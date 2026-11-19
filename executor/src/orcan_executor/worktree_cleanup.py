"""Shared conservative check before removing an executor worktree."""

import hashlib
import os
import subprocess
from pathlib import Path


def is_clean(worktree: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(worktree), "status", "--porcelain", "--untracked-files=all", "--ignored"],
        capture_output=True,
        timeout=30,
    )
    return result.returncode == 0 and not result.stdout


def removable(worktree: Path, definition: dict) -> bool:
    """Allow only reviewed ignored output directories in an otherwise clean tree."""
    allowed = definition.get("cleanup_ignored", [])
    if not allowed:
        return is_clean(worktree)
    result = subprocess.run(
        [
            "git",
            "-C",
            str(worktree),
            "status",
            "--porcelain",
            "-z",
            "--untracked-files=normal",
            "--ignored",
        ],
        capture_output=True,
        timeout=30,
    )
    if result.returncode:
        return False
    for record in result.stdout.split(b"\0"):
        if not record:
            continue
        if not record.startswith(b"!! "):
            return False
        relative = Path(os.fsdecode(record[3:]).rstrip("/"))
        if not any(relative.is_relative_to(Path(path)) for path in allowed):
            return False
        # An output root must be a real directory, never an ignored file/link.
        for path in allowed:
            root = worktree / path
            if relative.is_relative_to(Path(path)) and (root.is_symlink() or not root.is_dir()):
                return False
    return True


def archived_reports(
    worktree: Path, archive: Path, definition: dict, *, dry_run: bool = False
) -> int:
    """Opt-in removal of untracked JUnit files only after byte-identical archival."""

    def digest(path):
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").digest()

    if any(parent.is_symlink() for parent in [archive, *archive.parents]):
        return 0
    evidence = {
        digest(path) for path in archive.glob("*.xml") if path.is_file() and not path.is_symlink()
    }
    removed = 0
    for pattern in definition.get("junit", []):
        for path in worktree.glob(pattern):
            relative = path.relative_to(worktree)
            if not path.is_file() or any(
                parent.is_symlink() for parent in [path, *path.parents] if parent != worktree.parent
            ):
                continue
            tracked = subprocess.run(
                ["git", "-C", str(worktree), "ls-files", "--error-unmatch", "--", str(relative)],
                capture_output=True,
                timeout=10,
            )
            if tracked.returncode == 1 and digest(path) in evidence:
                removed += 1
                if dry_run:
                    continue
                path.unlink()
                parent = path.parent
                while parent != worktree:
                    try:
                        parent.rmdir()
                    except OSError:
                        break
                    parent = parent.parent
    return removed
