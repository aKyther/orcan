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


def test_worktree_plan_refuses_existing_destination(tmp_path: Path) -> None:
    repo = tmp_path / "parent"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
    root = tmp_path / "worktrees"
    destination = root / "parent" / "feature"
    destination.mkdir(parents=True)

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
