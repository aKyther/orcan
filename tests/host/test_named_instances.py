"""Named containers isolate runtime state but share the host resource catalog."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


def environment(tmp_path: Path) -> dict[str, str]:
    return {
        **os.environ,
        "HOME": str(tmp_path / "user"),
        "ORCAN_INSTANCES_ROOT": str(tmp_path / "orcan"),
        "ORCAN_HOME": str(tmp_path / "orcan"),
        "ORCAN_DATA": str(tmp_path / "shared"),
        "ORCAN_PROJECTS_ROOT": str(tmp_path / "shared" / "sandbox"),
        "ORCAN_STUDIO_DOCKER": "definitely-not-docker",
    }


def test_named_probes_share_sources_and_data_not_workspace_or_worktree_roots(
    tmp_path: Path,
) -> None:
    reports = []
    for name in ("developer", "tester"):
        result = subprocess.run(
            [str(ROOT / "bin/orcan"), "--instance", name, "studio", "probe", "--json"],
            env=environment(tmp_path),
            capture_output=True,
            text=True,
            check=True,
        )
        report = json.loads(result.stdout)
        assert report["runtime"]["docker"]["container"]["name"] == f"orcan-{name}"
        assert report["context"]["configuration"]["state"] == "missing"
        assert report["paths"]["home"] == str(tmp_path / "orcan" / "instances" / name)
        reports.append(report["paths"])
    assert reports[0]["data"] == reports[1]["data"]
    assert (
        reports[0]["cache"] == reports[1]["cache"] == str(tmp_path / "shared" / "cache")
    )
    assert reports[0]["projects_root"] == reports[1]["projects_root"]
    assert (
        reports[0]["workspace_metadata_root"] != reports[1]["workspace_metadata_root"]
    )
    assert reports[0]["managed_worktrees_root"] != reports[1]["managed_worktrees_root"]


@pytest.mark.parametrize(
    "name", ["../escape", "Developer", "-option", "a;b", "two words", "a" * 49]
)
def test_invalid_instance_names_are_rejected_before_creating_paths(
    tmp_path: Path, name: str
) -> None:
    result = subprocess.run(
        [str(ROOT / "bin/orcan"), "--instance", name, "version"],
        env=environment(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert not (tmp_path / "orcan").exists()


def test_inventory_ignores_probed_only_and_symlinked_directories(
    tmp_path: Path,
) -> None:
    root = tmp_path / "orcan"
    directory = root / "instances" / "tester"
    directory.mkdir(parents=True)
    (directory / "orcan.config.json").write_text('{"workspaces": []}', encoding="utf-8")
    (root / "instances" / "checked-only").mkdir()
    (root / "instances" / "alias").symlink_to(directory, target_is_directory=True)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/repository/studio-instances.py"),
            "--root",
            str(root),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert [item["instance"] for item in json.loads(result.stdout)["instances"]] == [
        None,
        "tester",
    ]


def test_down_is_scoped_to_named_compose_project_without_volume_removal(
    tmp_path: Path,
) -> None:
    binaries = tmp_path / "bin"
    binaries.mkdir()
    docker = binaries / "docker-stub.sh"
    log = tmp_path / "commands"
    docker.write_text(
        'docker() { printf "%s\\n" "$*" >> "$TEST_DOCKER_LOG"; }\n', encoding="utf-8"
    )
    docker.chmod(0o755)
    env = {
        **environment(tmp_path),
        "PATH": f"{binaries}:{os.environ['PATH']}",
        "TEST_DOCKER_LOG": str(log),
        "BASH_ENV": str(docker),
    }
    result = subprocess.run(
        [str(ROOT / "bin/orcan"), "--instance", "tester", "down"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert log.exists(), result.stdout + result.stderr
    operations = [line for line in log.read_text().splitlines() if " down " in line]
    assert operations
    assert all("--project-name orcan-tester " in line for line in operations)
    assert all("--volumes" not in line for line in operations)


def test_instance_selector_refuses_symlinked_config(tmp_path: Path) -> None:
    parent = tmp_path / "orcan" / "instances"
    parent.mkdir(parents=True)
    (parent / "tester").symlink_to(tmp_path, target_is_directory=True)
    result = subprocess.run(
        [str(ROOT / "bin/orcan"), "--instance", "tester", "version"],
        env=environment(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "symlink" in result.stderr


def test_real_worktrees_and_registries_are_instance_owned(tmp_path: Path) -> None:
    env = environment(tmp_path)
    repo = Path(env["ORCAN_PROJECTS_ROOT"]) / "api"
    repo.mkdir(parents=True)
    for args in (
        ["init", "-b", "main"],
        [
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "initial",
        ],
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    def cli(instance: str | None, *args: str, check: bool = True):
        command = [str(ROOT / "bin/orcan")]
        if instance:
            command += ["--instance", instance]
        return subprocess.run(
            command + list(args), env=env, text=True, capture_output=True, check=check
        )

    roots = {}
    for instance in (None, "developer", "tester"):
        name = instance or "default"
        cli(
            instance,
            "context",
            "worktree",
            "create",
            "--repo",
            str(repo),
            "--branch",
            f"{name}-feature",
            "--workspace",
            "same",
            "--project",
            "api",
        )
        report = json.loads(cli(instance, "studio", "probe", "--json").stdout)
        root = Path(report["paths"]["managed_worktrees_root"])
        roots[name] = root
        assert (root / "same" / "api").is_dir()
        registry = json.loads((root / "registry.json").read_text())
        assert len(registry["worktrees"]) == 1
        assert registry["worktrees"][0]["path"] == str(root / "same" / "api")
        parent = next(
            item
            for item in report["context"]["update_targets"]
            if item["path"] == str(repo)
        )
        assert parent["role"] == "worktree_parent"
        assert parent["worktree_count"] == 1

    target = roots["tester"] / "same" / "api"
    for owner in (None, "developer"):
        refused = cli(
            owner,
            "context",
            "worktree",
            "remove",
            "--path",
            str(target),
            "--force",
            check=False,
        )
        assert refused.returncode != 0
        assert "another instance" in refused.stderr
        assert target.exists()

    # Default prune must never sweep the nested named-instance namespace.
    cli(None, "context", "worktree", "prune", "--force")
    assert target.exists()
    assert (roots["developer"] / "same" / "api").exists()
    orphan = roots["developer"] / "unused" / "folder"
    orphan.mkdir(parents=True)
    (orphan / "scratch.txt").write_text("discardable test data")
    cli("developer", "context", "worktree", "prune", "--force")
    assert not orphan.exists()
    assert target.exists()
    assert (roots["default"] / "same" / "api").exists()
    listed = json.loads(
        cli(
            "tester",
            "studio",
            "worktree",
            "list",
            "--worktrees-root",
            str(roots["tester"]),
        ).stdout
    )
    assert [entry["path"] for entry in listed["worktrees"]] == [str(target)]
    cli(
        "developer",
        "context",
        "worktree",
        "remove",
        "--path",
        str(roots["developer"] / "same" / "api"),
        "--force",
    )
    assert not (roots["developer"] / "same" / "api").exists()
    assert target.exists()
    assert (roots["default"] / "same" / "api").exists()
    assert not json.loads((roots["developer"] / "registry.json").read_text())[
        "worktrees"
    ]


def test_probe_does_not_read_another_instance_registry(tmp_path: Path) -> None:
    env = environment(tmp_path)
    root = Path(env["ORCAN_PROJECTS_ROOT"]) / ".worktrees"
    root.mkdir(parents=True)
    (root / "registry.json").write_text(
        json.dumps(
            {
                "worktrees": [
                    {
                        "repo": str(ROOT),
                        "workspace": "legacy",
                        "project": "orcan",
                        "path": str(ROOT),
                    }
                ]
            }
        )
    )
    result = subprocess.run(
        [str(ROOT / "bin/orcan"), "--instance", "tester", "studio", "probe", "--json"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(result.stdout)
    assert report["context"]["update_targets"] == []
    assert not (root / "instances" / "tester").exists()
