"""Shared conservative check before removing an executor worktree."""

import subprocess
from pathlib import Path


def is_clean(worktree: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(worktree), "status", "--porcelain", "--untracked-files=all", "--ignored"],
        capture_output=True,
        timeout=30,
    )
    return result.returncode == 0 and not result.stdout
