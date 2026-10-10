"""Contract tests for the read-only Orcan Studio Sandbox probe."""

from __future__ import annotations

import pytest

import json
import os
import subprocess
from pathlib import Path

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


def test_git_snapshot_reads_real_upstream_counts_and_dirty_state(
    tmp_path, tracked_git_repo_factory
):
    from ._scripts_loader import load_script

    probe = load_script("studio-probe.py")
    repo = tracked_git_repo_factory(tmp_path / "repo")

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    git("remote", "add", "origin", "https://example.test/repo.git")
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    git("branch", "--set-upstream-to=origin/main", "main")
    git("commit", "--allow-empty", "-qm", "local")
    facts = probe.git_details(repo)
    assert (
        facts["branch"],
        facts["upstream"],
        facts["ahead"],
        facts["behind"],
        facts["dirty"],
    ) == ("main", "origin/main", 1, 0, False)
    (repo / "README").write_text("changed\n")
    assert probe.git_details(repo)["dirty"] is True
    git("checkout", "--detach")
    assert probe.git_details(repo)["branch"] is None


def test_probe_emits_only_the_versioned_json_contract(
    tmp_path: Path, git_repo_factory
) -> None:
    home = tmp_path / "home"
    project = git_repo_factory(tmp_path / "project")
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
    assert report["host"]["user"]
    assert report["context"]["configuration"]["path"] == str(home / "orcan.config.json")
    assert report["runtime"]["launch"] == {"recorded": False}
    assert report["control"]["operations"]["context_edit"] == {
        "available": True,
        "reason": "Orcan configuration is available for planned context changes.",
    }
    assert report["control"]["operations"]["parent_update"]["available"] is True
    assert [setting["id"] for setting in report["control"]["settings"]] == [
        "context",
        "lifecycle",
        "identity",
        "resources",
        "agents",
        "environment",
        "access",
        "git_auth",
    ]


def test_probe_reports_last_up_flags_without_credentials(tmp_path: Path) -> None:
    last_up = tmp_path / "last-up.env"
    last_up.write_text(
        "WITH_DOCKER=0\nWITH_GIT=1\nWITH_NETWORK=1\nWITH_TTYD=1\n"
        "WITH_TTYD_AUTH=1\nNETWORK_NAME=my\\ net\n"
        "WITH_GITHUB=1\nGITHUB_HOSTNAME=github.company.test\nWITH_GITLAB=1\nGITLAB_HOSTNAME=gitlab.company.test\n",
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
            f"--workspace-index={tmp_path / 'workspaces' / 'index.json'}",
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
        "github": "github.company.test",
        "gitlab": "gitlab.company.test",
        "network": "my net",
        "ttyd": True,
        "ttyd_auth": True,
    }


def test_probe_uses_the_last_synced_workspace_index_when_config_is_missing(
    tmp_path: Path,
    git_repo_factory,
) -> None:
    project = git_repo_factory(tmp_path / "project")
    index = tmp_path / "workspaces" / "index.json"
    index.parent.mkdir()
    index.write_text(
        json.dumps(
            {
                "workspaces": [
                    {
                        "name": "existing",
                        "projects": [{"name": "app", "path": str(project)}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "python3",
            "scripts/repository/studio-probe.py",
            "--protocol=1",
            "--version=test",
            f"--home={tmp_path / 'home'}",
            f"--data={tmp_path}",
            f"--projects-root={tmp_path}",
            f"--workspace-index={index}",
            f"--config={tmp_path / 'missing.json'}",
            f"--runtime={tmp_path / 'missing-runtime.json'}",
            "--image=orcan:test",
            "--container=orcan-test",
        ],
        cwd=ROOT,
        env={**os.environ, "ORCAN_STUDIO_DOCKER": "definitely-not-docker"},
        text=True,
        capture_output=True,
        check=True,
    )

    report = json.loads(result.stdout)
    assert report["context"]["configuration"]["state"] == "runtime_index"
    assert report["context"]["configuration"]["source"] == "runtime_index"
    assert report["context"]["configuration"]["editable"] is False
    assert report["control"]["operations"]["context_edit"]["available"] is False
    assert report["control"]["settings"][0]["state"] == "locked"
    assert report["paths"]["workspace_metadata_root"] == str(index.parent)
    workspace = report["context"]["workspaces"]
    assert workspace[0]["name"] == "existing"
    assert workspace[0]["projects"][0]["name"] == "app"
    assert workspace[0]["projects"][0]["path"] == str(project)
    assert workspace[0]["projects"][0]["kind"] == "git_repository"


def test_probe_marks_worktree_sources_and_clean_git_mounts_separately(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    source = tmp_path / "source"
    mount = tmp_path / "mount"
    plain_directory = tmp_path / "plain-directory"
    for repository in (source, mount):
        repository.mkdir()
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
    plain_directory.mkdir()
    config = home / "orcan.config.json"
    config.parent.mkdir()
    config.write_text(
        json.dumps(
            {
                "workspaces": [
                    {
                        "name": "dev",
                        "projects": [
                            {"path": str(source)},
                            {"path": str(mount)},
                            {"path": str(plain_directory)},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    projects_root = tmp_path / "sandbox"
    registry = projects_root / ".worktrees" / "registry.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps(
            {
                "worktrees": [
                    {
                        "workspace": "dev",
                        "project": "source",
                        "repo": str(source),
                        "path": str(projects_root / ".worktrees" / "dev" / "source"),
                        "branch": "feature/dev",
                    },
                    {
                        "workspace": "review",
                        "project": "source",
                        "repo": str(source),
                        "path": str(projects_root / ".worktrees" / "review" / "source"),
                        "branch": "review/dev",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "python3",
            "scripts/repository/studio-probe.py",
            "--protocol=1",
            "--version=test",
            f"--home={home}",
            f"--data={tmp_path}",
            f"--projects-root={projects_root}",
            f"--workspace-index={tmp_path / 'workspaces' / 'index.json'}",
            f"--config={config}",
            f"--runtime={tmp_path / 'missing.json'}",
            "--image=orcan:test",
            "--container=orcan-test",
        ],
        cwd=ROOT,
        env={**os.environ, "ORCAN_STUDIO_DOCKER": "definitely-not-docker"},
        text=True,
        capture_output=True,
        check=True,
    )

    targets = {
        target["path"]: target
        for target in json.loads(result.stdout)["context"]["update_targets"]
    }
    assert set(targets) == {str(source), str(mount)}
    assert targets[str(source)]["role"] == "worktree_parent"
    assert targets[str(source)]["worktree_count"] == 2
    assert targets[str(source)]["read_only"] is False
    assert targets[str(mount)]["role"] == "configured_mount"
    assert targets[str(mount)]["read_only"] is True
    assert targets[str(mount)]["eligible"] is True

    (mount / "local-change.txt").write_text("do not pull here\n", encoding="utf-8")
    dirty_result = subprocess.run(
        [
            "python3",
            "scripts/repository/studio-probe.py",
            "--protocol=1",
            "--version=test",
            f"--home={home}",
            f"--data={tmp_path}",
            f"--projects-root={projects_root}",
            f"--workspace-index={tmp_path / 'workspaces' / 'index.json'}",
            f"--config={config}",
            f"--runtime={tmp_path / 'missing.json'}",
            "--image=orcan:test",
            "--container=orcan-test",
        ],
        cwd=ROOT,
        env={**os.environ, "ORCAN_STUDIO_DOCKER": "definitely-not-docker"},
        text=True,
        capture_output=True,
        check=True,
    )
    dirty_targets = {
        target["path"]
        for target in json.loads(dirty_result.stdout)["context"]["update_targets"]
    }
    assert str(source) in dirty_targets
    assert str(mount) not in dirty_targets


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
