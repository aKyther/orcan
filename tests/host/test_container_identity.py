"""Frozen identity creation, sync and workspace instruction integration."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from _scripts_loader import load_script

apply_config = load_script("apply-config.py")
from orcan.identity import validate_identity
from orcan.reconcile import apply_workspaces

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts/repository"
IDENTITY = {
    "id": "8f2c7e2a-8bcf-44e9-bfc7-4c1fe75ed871",
    "version": 1,
    "name": "Reviewer",
    "description": "Check correctness independently",
    "instructions": "Check failure paths. Report evidence before conclusions.",
}


def run(script, *args, creation=False):
    env = dict(os.environ)
    env.pop("ORCAN_STUDIO_CREATE_RUNTIME", None)
    if creation:
        env["ORCAN_STUDIO_CREATE_RUNTIME"] = "1"
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *map(str, args)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "../../elsewhere"),
        ("version", True),
        ("version", 0),
        ("name", "Review\n## Override"),
        ("instructions", ""),
        ("instructions", "ą" * 16385),
    ],
)
def test_invalid_identity_is_rejected_before_configuration_creation(
    tmp_path, field, value
):
    identity = dict(IDENTITY, **{field: value})
    with pytest.raises(ValueError):
        validate_identity(identity)
    config = tmp_path / "orcan.config.json"
    report = run(
        "studio-enclave.py",
        "apply",
        "--config",
        config,
        "--identity-json",
        json.dumps(identity),
        "--yes",
    )
    assert report.returncode != 0
    assert not config.exists()


@pytest.mark.parametrize("identity", [None, IDENTITY])
def test_sync_freezes_default_or_identity_and_rejects_later_changes(tmp_path, identity):
    (tmp_path / ".env.example").write_text("USER_UID=1000\nUSER_GID=1000\n")
    config = tmp_path / "orcan.config.json"
    args = ["apply", "--config", config, "--yes"]
    if identity:
        args.extend(["--identity-json", json.dumps(identity)])
    assert run("studio-enclave.py", *args).returncode == 0
    sync_args = ["--root", tmp_path, "--config", config]
    first = run("apply-config.py", *sync_args, creation=True)
    assert first.returncode == 0, first.stderr
    runtime = tmp_path / "mounts/runtime-config.json"
    before = runtime.read_bytes()
    assert json.loads(before)["identity"] == identity
    assert run("apply-config.py", *sync_args).returncode == 0
    changed = dict(IDENTITY, version=2) if identity else IDENTITY
    config.write_text(json.dumps({"workspaces": [], "identity": changed}))
    rejected = run("apply-config.py", *sync_args, creation=True)
    assert rejected.returncode != 0
    assert "immutable" in rejected.stderr
    assert runtime.read_bytes() == before
    if identity:
        config.write_text(json.dumps({"workspaces": []}))
        assert run("apply-config.py", *sync_args).returncode != 0


def test_custom_identity_cannot_be_added_by_ordinary_sync(tmp_path):
    (tmp_path / ".env.example").write_text("USER_UID=1000\n")
    config = tmp_path / "orcan.config.json"
    config.write_text(json.dumps({"workspaces": [], "identity": IDENTITY}))
    report = run("apply-config.py", "--root", tmp_path, "--config", config)
    assert report.returncode != 0
    assert "only be assigned" in report.stderr
    assert not (tmp_path / "mounts/frozen-identity.json").exists()


def test_current_and_future_workspaces_keep_base_and_repository_rules(tmp_path):
    templates = ROOT / "docker/rootfs/opt/cursor-defaults/templates/workspace"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("Repository-specific rules\n")
    cfg = {"identity": IDENTITY, "workspaces": []}
    for name in ["current", "future"]:
        workspace = tmp_path / "workspaces" / name
        cfg["workspaces"].append(
            {
                "name": name,
                "root": str(workspace),
                "tmux_session": name,
                "projects": [
                    {
                        "name": "app",
                        "path": str(repo),
                        "workspace_path": str(workspace / "app"),
                    }
                ],
            }
        )
        apply_workspaces(cfg, templates, tmp_path / "workspaces")
    for ws in cfg["workspaces"]:
        root = Path(ws["root"])
        before = (root / "AGENTS.md").read_text()
        assert "project's `AGENTS.md` / `CLAUDE.md` is SoT" in before
        assert IDENTITY["instructions"] in before
        assert (root / "CLAUDE.md").read_text() == before
        custom = root / ".cursor/rules/custom.mdc"
        custom.write_text("Keep my custom rule")
        apply_workspaces(cfg, templates, tmp_path / "workspaces")
        assert custom.read_text() == "Keep my custom rule"
        assert (root / "AGENTS.md").read_text() == before
    assert (repo / "AGENTS.md").read_text() == "Repository-specific rules\n"


def test_rollback_only_removes_matching_identity_seed_and_freeze(tmp_path):
    config = tmp_path / "orcan.config.json"
    args = ["--config", config, "--identity-json", json.dumps(IDENTITY), "--yes"]
    assert run("studio-enclave.py", "apply", *args).returncode == 0
    frozen = tmp_path / "mounts/frozen-identity.json"
    frozen.parent.mkdir()
    frozen.write_text(json.dumps(IDENTITY))
    wrong = [
        "--config",
        config,
        "--identity-json",
        json.dumps(dict(IDENTITY, version=2)),
        "--yes",
    ]
    assert run("studio-enclave.py", "rollback", *wrong).returncode != 0
    assert frozen.exists() and config.exists()
    assert run("studio-enclave.py", "rollback", *args).returncode == 0
    assert not frozen.exists() and not config.exists()


@pytest.mark.parametrize("supported", [False, True])
def test_cli_identity_plan_checks_image_support_before_writing(tmp_path, supported):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    docker = binaries / "docker-stub.sh"
    docker.write_text(
        "docker() { printf '%s\\n' '" + ("1" if supported else "") + "'; }\n"
    )
    docker.chmod(0o755)
    home = tmp_path / "home"
    result = subprocess.run(
        [
            str(ROOT / "bin/orcan"),
            "--instance",
            "reviewer",
            "studio",
            "enclave",
            "plan",
            "--image",
            "orcan:identity",
            "--identity-json",
            json.dumps(IDENTITY),
        ],
        env={
            **os.environ,
            "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
            "ORCAN_HOME": str(home),
            "ORCAN_INSTANCES_ROOT": str(home),
            "ORCAN_DATA": str(tmp_path / "data"),
            "BASH_ENV": str(docker),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert not (home / "instances/reviewer/orcan.config.json").exists()
    if supported:
        assert result.returncode == 0, result.stderr
        assert any(
            "Reviewer v1" in change
            for change in json.loads(result.stdout)["plan"]["changes"]
        )
    else:
        assert result.returncode != 0
        assert "does not support identities" in result.stderr


def test_probe_uses_frozen_runtime_identity_instead_of_unsynced_edit(tmp_path):
    home = tmp_path / "home"
    mounts = home / "mounts"
    mounts.mkdir(parents=True)
    (home / "orcan.config.json").write_text(
        json.dumps({"workspaces": [], "identity": dict(IDENTITY, version=2)})
    )
    (mounts / "runtime-config.json").write_text(
        json.dumps({"workspaces": [], "identity": IDENTITY})
    )
    result = subprocess.run(
        [str(ROOT / "bin/orcan"), "studio", "probe", "--json"],
        env={
            **os.environ,
            "ORCAN_HOME": str(home),
            "ORCAN_DATA": str(tmp_path / "data"),
            "ORCAN_STUDIO_DOCKER": "definitely-not-docker",
        },
        text=True,
        capture_output=True,
        check=True,
    )
    report = json.loads(result.stdout)
    assert report["context"]["identity"] == IDENTITY
    assert report["capabilities"]["identity_templates"]
    setting = next(
        setting
        for setting in report["control"]["settings"]
        if setting["id"] == "identity"
    )
    assert setting["state"] == "locked"
    assert setting["value"] == "Reviewer v1"
