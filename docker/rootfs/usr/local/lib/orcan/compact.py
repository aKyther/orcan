"""Brief budgets and lossless archival; summarisation belongs to the active agent."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

MAX_WORDS = 800
MAX_BYTES = 8000


def workspace_root(value: str | None = None) -> Path:
    explicit = value or os.environ.get("ORCAN_WORKSPACE_ROOT")
    if explicit:
        root = Path(explicit).resolve()
    else:
        cwd = Path.cwd().resolve()
        root = next(
            (p for p in (cwd, *cwd.parents) if (p / ".manifest.json").is_file()), cwd
        )
    if not (root / ".manifest.json").is_file():
        raise ValueError("Not an Orcan workspace: .manifest.json is missing")
    return root


def brief_path(root: Path) -> Path:
    directory = root / ".orcan"
    path = directory / "session-brief.md"
    if directory.is_symlink() or path.is_symlink():
        raise ValueError("Refusing a symlinked brief or .orcan directory")
    return path


def measure(data: bytes) -> dict:
    words = len(data.decode("utf-8").split())
    return {
        "words": words,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "needs_compact": words > MAX_WORDS or len(data) > MAX_BYTES,
    }


def check(root: Path) -> dict:
    path = brief_path(root)
    if not path.exists():
        return {"exists": False, "needs_compact": False}
    return {"exists": True, **measure(path.read_bytes())}


def apply(root: Path, candidate: Path, expected: str) -> dict:
    path = brief_path(root)
    if candidate.is_symlink() or candidate.resolve() == path.resolve():
        raise ValueError("Use a separate regular candidate file")
    proposed = candidate.read_bytes()
    stats = measure(proposed)
    if not proposed.strip() or stats["needs_compact"]:
        raise ValueError(
            f"Candidate must be non-empty and within {MAX_WORDS} words / {MAX_BYTES} bytes"
        )
    lock = path.parent / "compact.lock"
    if lock.is_symlink():
        raise ValueError("Refusing a symlinked compact lock")
    with lock.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        original = path.read_bytes()
        if measure(original)["sha256"] != expected:
            raise ValueError("Brief changed; reread it and prepare a fresh summary")
        if len(proposed) >= len(original):
            raise ValueError("Candidate must be smaller than the current brief")
        archive = path.parent / "brief-history"
        if archive.is_symlink():
            raise ValueError("Refusing a symlinked brief archive")
        archive.mkdir(mode=0o700, exist_ok=True)
        # Keep history out of ordinary rg scans and accidental Git additions.
        for name in (".ignore", ".gitignore"):
            try:
                with (archive / name).open("x") as stream:
                    stream.write("*\n")
            except FileExistsError:
                pass
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        backup = archive / f"{stamp}-{uuid4().hex[:8]}.md"
        # Archive successfully before replacing anything. Never prune history here.
        with backup.open("xb") as stream:
            os.chmod(backup, 0o600)
            stream.write(original)
            stream.flush()
            os.fsync(stream.fileno())
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(proposed)
                stream.flush()
                os.fsync(stream.fileno())
            if path.is_symlink() or path.read_bytes() != original:
                raise ValueError(
                    "Brief changed during compaction; original retained in archive"
                )
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return {"archive": str(backup), **stats}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace", help="Workspace root; otherwise environment or nearest manifest"
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--check",
        action="store_true",
        help="Report budget and hash (default; no writes)",
    )
    action.add_argument(
        "--apply",
        metavar="FILE",
        type=Path,
        help="Install an agent-written summary, archiving the old brief",
    )
    parser.add_argument(
        "--expected-sha256", help="Hash from --check; required with --apply"
    )
    args = parser.parse_args(argv)
    if bool(args.apply) != bool(args.expected_sha256):
        parser.error("--apply and --expected-sha256 must be used together")
    try:
        root = workspace_root(args.workspace)
        result = (
            apply(root, args.apply, args.expected_sha256) if args.apply else check(root)
        )
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
