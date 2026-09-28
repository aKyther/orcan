"""Contract tests for the read-only Orcan Studio Sandbox probe."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_probe_emits_only_the_versioned_json_contract(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(project),
            "remote",
            "add",
            "origin",
            "git@example.test:team/app.git",
        ],
        check=True,
    )
    (home / "orcan.config.json").parent.mkdir(parents=True)
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
    env = {
        **os.environ,
        "ORCAN_HOME": str(home),
        "ORCAN_DATA": str(tmp_path / "data"),
        "ORCAN_STUDIO_DOCKER": "definitely-not-docker",
    }
    result = subprocess.run(
        ["./bin/orcan", "studio", "probe", "--json"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["protocol"] == {
        "name": "orcan-studio",
        "version": 1,
        "methods": ["probe"],
    }
    assert report["runtime"]["docker"]["container"]["state"] == "unavailable"
    assert report["capabilities"]["managed_projects"]
    assert report["context"]["workspaces"][0]["projects"][0]["kind"] == "git_repository"
    repository = report["context"]["repositories"][0]
    assert repository["origin_url"] == "git@example.test:team/app.git"
    assert repository["bindings"][0]["workspace"] == "dev"
    assert report["paths"]["managed_worktrees_root"].endswith("sandbox/.worktrees")
    assert report["runtime"]["launch"] == {"recorded": False}


def test_probe_reports_last_up_flags_without_credentials(tmp_path: Path) -> None:
    last_up = tmp_path / "last-up.env"
    last_up.write_text(
        "WITH_DOCKER=0\nWITH_GIT=1\nWITH_NETWORK=1\nWITH_TTYD=1\n"
        "WITH_TTYD_AUTH=1\nNETWORK_NAME=my\\ net\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "python3",
            "scripts/repository/studio-probe.py",
            "--protocol=1",
            "--version=test",
            f"--home={tmp_path}",
            f"--data={tmp_path}",
            f"--projects-root={tmp_path}",
            f"--config={tmp_path / 'missing.json'}",
            f"--runtime={tmp_path / 'missing.json'}",
            "--image=orcan:test",
            "--container=orcan-test",
            f"--last-up={last_up}",
        ],
        cwd=ROOT,
        env={**os.environ, "ORCAN_STUDIO_DOCKER": "definitely-not-docker"},
        text=True,
        capture_output=True,
        check=True,
    )

    assert json.loads(result.stdout)["runtime"]["launch"] == {
        "recorded": True,
        "docker": False,
        "git": True,
        "network": "my net",
        "ttyd": True,
        "ttyd_auth": True,
    }


def test_probe_requires_the_json_protocol_flag() -> None:
    result = subprocess.run(
        ["./bin/orcan", "studio", "probe"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "usage: orcan studio probe --json" in result.stderr
