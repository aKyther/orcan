"""Contract tests for Orcan Studio workspace membership plans."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_settings(home: Path, *arguments: str) -> dict[str, object]:
    result = subprocess.run(
        ["./bin/orcan", "studio", "settings", *arguments],
        cwd=ROOT,
        env={**os.environ, "ORCAN_HOME": str(home)},
        text=True,
        capture_output=True,
        check=False,
    )
    return json.loads(result.stdout)


def make_home(tmp_path: Path) -> tuple[Path, Path]:
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "app"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    (home / "orcan.config.json").write_text(
        json.dumps(
            {
                "workspaces": [
                    {"name": "dev", "projects": [{"name": "app", "path": str(project)}]}
                ]
            }
        ),
        encoding="utf-8",
    )
    return home, project


def test_attach_to_a_new_workspace_is_planned_as_creating_it(tmp_path: Path) -> None:
    home, project = make_home(tmp_path)

    plan = run_settings(
        home, "project-add-plan", "--workspace", "review", "--project", str(project)
    )["plan"]

    assert plan["ready"] and plan["creates_workspace"]
    assert plan["changes"][0] == "create workspace review"


def test_attach_blocks_an_already_attached_project(tmp_path: Path) -> None:
    home, project = make_home(tmp_path)

    plan = run_settings(
        home, "project-add-plan", "--workspace", "dev", "--project", str(project)
    )["plan"]

    assert not plan["ready"]
    assert plan["blockers"] == ["project is already attached"]


def test_mount_mode_allows_a_plain_directory_in_multiple_workspaces(
    tmp_path: Path,
) -> None:
    home, project = make_home(tmp_path)
    shared = tmp_path / "shared-config"
    shared.mkdir()

    plan = run_settings(
        home,
        "project-add-plan",
        "--workspace",
        "ops",
        "--project",
        str(shared),
        "--project-mode",
        "mount",
    )["plan"]

    assert plan["ready"]
    assert plan["project_mode"] == "mount"
    assert "mount directory as-is" in plan["changes"]
    # A Git project can still be shared with another workspace as the same path.
    git_plan = run_settings(
        home,
        "project-add-plan",
        "--workspace",
        "ops",
        "--project",
        str(project),
        "--project-mode",
        "mount",
    )["plan"]
    assert git_plan["ready"]


def test_detach_removes_membership_but_keeps_files(tmp_path: Path) -> None:
    home, project = make_home(tmp_path)

    result = run_settings(
        home,
        "project-detach-apply",
        "--workspace",
        "dev",
        "--project",
        str(project),
        "--yes",
    )

    assert result["ok"]
    config = json.loads((home / "orcan.config.json").read_text(encoding="utf-8"))
    assert config["workspaces"][0]["projects"] == []
    assert (project / ".git").exists()
