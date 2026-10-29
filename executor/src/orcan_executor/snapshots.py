"""Explicit, bounded source snapshots for directories without a project Git repository."""

import fcntl
import hashlib
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

from . import profiles
from .settings import state_dir

MAX_FILES = 512
MAX_BYTES = 32 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024


def lock_path(name: str = "") -> Path:
    # One stable inode also protects cleanup against a concurrent submit.
    root = state_dir()
    root.mkdir(parents=True, exist_ok=True)
    return root / "directory-snapshots.lock"


@contextmanager
def snapshot(source: Path, includes: list[str]):
    source = source.resolve(strict=True)
    names = sorted(set([profiles.CONFIG, *includes]))
    if not includes or len(names) > MAX_FILES:
        raise ValueError("Directory snapshots require explicit --include files (at most 512)")
    files = []
    size = 0
    digest = hashlib.sha256()
    # Different source directories remain distinct even with identical file contents.
    digest.update(str(source).encode())
    for name in names:
        relative = profiles.relative(name)
        if any(part.lower() == ".git" for part in relative.parts) or any(
            part.lower() == ".env"
            or part.lower().startswith(".env.")
            or part.lower() in {"runtime.conf", "id_rsa", "id_ed25519"}
            for part in relative.parts
        ):
            raise ValueError("Secret and Git metadata paths cannot enter directory snapshots")
        path = source / relative
        if path.resolve(strict=True) != path or not path.is_file():
            raise ValueError("Snapshot includes must be regular files without symlink components")
        before = path.stat()
        if before.st_size > MAX_FILE_BYTES:
            raise ValueError("Snapshot file exceeds 8 MiB")
        with path.open("rb") as stream:
            content = stream.read(MAX_FILE_BYTES + 1)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ino,
        ) or len(content) > MAX_FILE_BYTES:
            raise ValueError("Source changed during snapshot; retry submission")
        size += len(content)
        if size > MAX_BYTES:
            raise ValueError("Directory snapshot exceeds 32 MiB")
        executable = bool(before.st_mode & 0o111)
        digest.update(name.encode() + b"\0" + str(len(content)).encode() + b"\0")
        digest.update(bytes([executable]))
        digest.update(content)
        files.append((relative, content, executable))
    name = digest.hexdigest()
    root = state_dir() / "snapshots"
    root.mkdir(parents=True, exist_ok=True)
    destination = root / name
    with lock_path(name).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not destination.exists():
            temporary = Path(tempfile.mkdtemp(prefix=".preparing-", dir=root))
            try:
                for relative, content, executable in files:
                    target = temporary / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
                    target.chmod(0o755 if executable else 0o644)
                environment = {
                    **os.environ,
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_AUTHOR_NAME": "Orcan snapshot",
                    "GIT_AUTHOR_EMAIL": "snapshot@orcan.invalid",
                    "GIT_COMMITTER_NAME": "Orcan snapshot",
                    "GIT_COMMITTER_EMAIL": "snapshot@orcan.invalid",
                    "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+00:00",
                    "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+00:00",
                }
                for arguments in (
                    ["init", "-q"],
                    ["add", "--force", "--all"],
                    [
                        "-c",
                        "core.hooksPath=/dev/null",
                        "-c",
                        "commit.gpgsign=false",
                        "commit",
                        "-qm",
                        "Explicit directory snapshot",
                    ],
                ):
                    subprocess.run(
                        ["git", "-C", str(temporary), *arguments],
                        env=environment,
                        check=True,
                        capture_output=True,
                    )
                (temporary / ".git/orcan-directory-snapshot").write_text(str(source))
                temporary.rename(destination)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
        yield destination


def prune_snapshots() -> int:
    """Remove old owned source caches only when no job still refers to them."""
    import time

    from . import store
    from .settings import retention_seconds

    root = state_dir() / "snapshots"
    if not root.exists():
        return 0
    removed = 0
    with lock_path().open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        for path in root.iterdir():
            marker = path / ".git/orcan-directory-snapshot"
            if path.is_symlink() or not path.is_dir() or not marker.is_file():
                continue
            if time.time() - marker.stat().st_mtime < retention_seconds():
                continue
            with store.database() as db:
                active = db.execute(
                    "SELECT COUNT(*) FROM jobs WHERE git_dir=?", (str(path / ".git"),)
                ).fetchone()[0]
            if active:
                continue
            shutil.rmtree(path)
            removed += 1
    return removed
