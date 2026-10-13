"""Workspace labels for existing Git worktrees."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


def worktree_name(path: Path) -> str:
    """Keep ordinary directory names; label linked worktrees by repo and branch."""
    if not (path / ".git").is_file():
        return path.name

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else ""

    try:
        common = git("rev-parse", "--path-format=absolute", "--git-common-dir")
        git_dir = git("rev-parse", "--absolute-git-dir")
        if not common or Path(common) == Path(git_dir):
            return path.name
        branch = git("symbolic-ref", "--quiet", "--short", "HEAD")
        suffix = branch or "detached-" + git("rev-parse", "--short", "HEAD")
    except (OSError, subprocess.TimeoutExpired):
        return path.name
    if not common:
        return path.name
    common_path = Path(common)
    repo = common_path.parent.name if common_path.name == ".git" else common_path.name

    def segment(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-") or "branch"

    return f"{segment(repo)}--{segment(suffix)}"


def attachment_name(path: Path, projects: list[dict], *, force: bool = False) -> str:
    """Preserve existing labels and avoid replacing sibling worktrees."""
    for project in projects:
        if project.get("path") and Path(project["path"]).resolve() == path.resolve():
            return project["name"]
    base = worktree_name(path)
    names = {project.get("name") for project in projects}
    name = base
    number = 2
    if not force and (path / ".git").is_file():
        while name in names:
            name = f"{base}--{number}"
            number += 1
    return name
