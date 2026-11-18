"""Shared conservative check before removing an executor worktree."""

import hashlib
import subprocess
from pathlib import Path


def is_clean(worktree: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(worktree), "status", "--porcelain", "--untracked-files=all", "--ignored"],
        capture_output=True,
        timeout=30,
    )
    return result.returncode == 0 and not result.stdout


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
