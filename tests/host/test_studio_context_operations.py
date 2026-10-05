"""Host tests for read-only Studio context plans."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def studio_script(name: str, *arguments: str) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "repository" / name), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_import_plan_proposes_managed_root(tmp_path: Path) -> None:
    report = studio_script(
        "studio-import.py",
        "plan",
        "--source",
        "https://example.test/team/demo.git",
        "--projects-root",
        str(tmp_path / "sandbox"),
    )

    plan = report["plan"]
    assert plan["ready"] is True
    assert plan["default_destination"] is True
    assert plan["destination"].endswith("sandbox/demo")


def test_import_plan_uses_an_orcan_reported_parent_under_the_managed_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "sandbox"
    parent = root / "new"
    parent.mkdir(parents=True)

    report = studio_script(
        "studio-import.py",
        "plan",
        "--source",
        "https://example.test/team/demo.git",
        "--projects-root",
        str(root),
        "--parent",
        str(parent),
    )

    plan = report["plan"]
    assert plan["ready"] is True
    assert plan["parent"] == str(parent)
    assert plan["destination"] == str(parent / "demo")


def test_worktree_plan_refuses_existing_destination(tmp_path: Path) -> None:
    repo = tmp_path / "parent"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
    root = tmp_path / "worktrees"
    destination = root / "api" / "parent--feature"
    destination.mkdir(parents=True)
    subprocess.run(
        ["git", "-C", str(destination), "init", "-q"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(destination), "checkout", "-q", "-b", "feature"],
        check=True,
        capture_output=True,
    )

    report = studio_script(
        "studio-worktree.py",
        "plan",
        "--repo",
        str(repo),
        "--branch",
        "feature",
        "--worktrees-root",
        str(root),
        "--workspace",
        "api",
    )

    assert report["plan"]["ready"] is False
    assert "already exists" in report["plan"]["blockers"][0]


def test_worktree_plan_names_multiple_branches_of_one_repo_in_one_workspace(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "api"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
    root = tmp_path / "worktrees"

    first = studio_script(
        "studio-worktree.py",
        "plan",
        "--repo",
        str(repo),
        "--branch",
        "feature/auth",
        "--worktrees-root",
        str(root),
        "--workspace",
        "platform",
    )["plan"]
    second = studio_script(
        "studio-worktree.py",
        "plan",
        "--repo",
        str(repo),
        "--branch",
        "fix/cache",
        "--worktrees-root",
        str(root),
        "--workspace",
        "platform",
    )["plan"]

    assert first["project"] == "api--feature-auth"
    assert second["project"] == "api--fix-cache"
    assert first["destination"] == str(root / "platform" / "api--feature-auth")
    assert second["destination"] == str(root / "platform" / "api--fix-cache")
