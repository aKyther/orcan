"""Contract tests for Studio's safe parent-update plan."""

from __future__ import annotations

import pytest

import json
import subprocess
from pathlib import Path


pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "repository" / "studio-parent.py"


def run(*arguments: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(arguments), cwd=cwd, text=True, capture_output=True, check=True
    )


def make_parent(tmp_path: Path, git_repo_factory) -> Path:
    origin = tmp_path / "origin.git"
    parent = git_repo_factory(tmp_path / "parent")
    run("git", "init", "--bare", "-q", str(origin))
    run("git", "config", "user.email", "studio@example.test", cwd=parent)
    run("git", "config", "user.name", "Studio test", cwd=parent)
    (parent / "README.md").write_text("parent\n", encoding="utf-8")
    run("git", "add", "README.md", cwd=parent)
    run("git", "commit", "-qm", "initial", cwd=parent)
    run("git", "remote", "add", "origin", str(origin), cwd=parent)
    run("git", "push", "-qu", "origin", "main", cwd=parent)
    return parent


def plan(parent: Path) -> dict[str, object]:
    result = run(
        "python3", str(SCRIPT), "plan", "--path", str(parent), "--branch", "main"
    )
    return json.loads(result.stdout)


def test_parent_plan_is_read_only_and_requires_a_clean_default_branch(
    tmp_path: Path,
    git_repo_factory,
) -> None:
    parent = make_parent(tmp_path, git_repo_factory)
    report = plan(parent)

    assert report["ok"] is True
    assert report["plan"]["ready"] is True
    assert report["plan"]["operation"] == "git pull --ff-only"

    (parent / "README.md").write_text("changed\n", encoding="utf-8")
    dirty = plan(parent)
    assert dirty["plan"]["ready"] is False
    assert "uncommitted" in dirty["plan"]["blockers"][0]
