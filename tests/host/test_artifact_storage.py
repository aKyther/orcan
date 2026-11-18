"""Host storage settings prepare mounts explicitly and never create missing sources."""

from pathlib import Path

import pytest
from orcan import storage_config

from ._scripts_loader import load_script

model_module = load_script("settings_model.py")
apply = load_script("apply-config.py")
planner = load_script("up-plan.py")


@pytest.mark.parametrize(
    "value",
    [
        {"path": "relative"},
        {"path": "/tmp"},
        {"path": "/proc/data"},
        {"path": "/"},
        {"path": "/mnt/$STORAGE"},
        {"path": "/mnt/data\nother"},
        {"require_mount": "yes"},
        {"unknown": True},
        {"path": "/mnt/storage/data", "mount_path": "/other"},
        {"mount_path": "relative"},
        {"mount_path": True},
    ],
)
def test_invalid_storage_configuration_is_rejected(value):
    with pytest.raises(ValueError):
        storage_config.resolve(value)


def test_storage_draft_save_and_preview_do_not_touch_mount(tmp_path):
    path = tmp_path / "orcan.config.json"
    path.write_text('{"workspaces":[]}')
    before = path.read_bytes()
    model = model_module.SettingsModel(path)
    model.set_storage("path", "/mnt/company artifacts")
    assert path.read_bytes() == before
    assert "orcan up --plan" in model.next_actions()
    assert "orcan build" not in model.next_actions()
    assert not (tmp_path / "mounts").exists()
    model.save()
    report = planner.preview(path, tmp_path, [])
    mount = next(
        row for row in report["mounts"] if row["purpose"] == "artifact storage"
    )
    assert mount["source"] == mount["target"] == "/mnt/company artifacts"
    assert mount["require_mount"] and mount["create_host_path"] is False
    assert not (tmp_path / "mounts").exists()
    model.set_storage("path", "")
    assert model.data["storage"]["path"] == ""


def test_generated_storage_bind_preserves_spaces_and_never_creates_source(tmp_path):
    output = apply.write_compose_projects(
        [], tmp_path, storage_root="/mnt/remote volume:one"
    )
    assert 'source: "/mnt/remote volume:one"' in output
    assert 'target: "/mnt/remote volume:one"' in output
    assert "create_host_path: false" in output


def test_missing_storage_stops_without_creating_directory(tmp_path):
    target = tmp_path / "missing"
    with pytest.raises(ValueError, match="unavailable"):
        storage_config.check(target, require_mount=False)
    assert not target.exists()


def test_mount_guard_checks_parent_mount_and_rejects_unmounted_fallback(
    tmp_path, monkeypatch
):
    target = tmp_path / "storage"
    target.mkdir()
    monkeypatch.setattr(Path, "is_mount", lambda self: False)
    with pytest.raises(ValueError, match="not mounted"):
        storage_config.check(target)
    assert storage_config.check(target, False) == target
    monkeypatch.setattr(Path, "is_mount", lambda self: self == tmp_path)
    with pytest.raises(ValueError, match="not mounted"):
        storage_config.check(
            target
        )  # A different parent filesystem is not the intended mount.
    assert storage_config.check(target, mount_path=tmp_path) == target


def test_prepare_namespaces_and_preserves_other_data(tmp_path):
    root = tmp_path / "storage"
    root.mkdir()
    (root / "keep").write_text("user data")
    scratch = storage_config.prepare(root, False, "review")
    assert scratch == root / "orcan/review/scratch"
    assert scratch.is_dir()
    assert (root / "keep").read_text() == "user data"


def test_prepare_refuses_symlink_namespace(tmp_path):
    root = tmp_path / "storage"
    root.mkdir()
    (root / "orcan").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        storage_config.prepare(root, False)


@pytest.mark.integration
def test_startup_rejects_missing_storage_before_touching_container(tmp_path):
    import os
    import subprocess

    root = Path(__file__).resolve().parents[2]
    missing = tmp_path / "missing"
    script = """
set -Eeuo pipefail
source "$ORCAN_ROOT/cli/lib/startup.sh"
orcan_load_config() { :; }
orcan_require_generated() { :; }
orcan_host_python() { python3 "$@"; }
docker() { echo UNEXPECTED_DOCKER; return 99; }
orcan_startup_check_inputs
"""
    result = subprocess.run(
        ["bash", "-c", script],
        env={
            **os.environ,
            "ORCAN_ROOT": str(root),
            "ORCAN_STORAGE_ROOT": str(missing),
            "ORCAN_STORAGE_REQUIRE_MOUNT": "1",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "unavailable" in result.stderr
    assert "UNEXPECTED_DOCKER" not in result.stdout
    assert not missing.exists()


def test_local_storage_preview_does_not_claim_mount_requirement(tmp_path):
    path = tmp_path / "orcan.config.json"
    path.write_text(
        '{"workspaces":[],"storage":{"path":"/mnt/local-data","require_mount":false}}'
    )
    report = planner.preview(path, tmp_path, [])
    mount = next(
        row for row in report["mounts"] if row["purpose"] == "artifact storage"
    )
    assert mount["require_mount"] is False


@pytest.mark.parametrize("path", ["/run/media/team/sshfs", "/tmp/sshfs"])
def test_dedicated_mount_directories_are_supported(path):
    assert storage_config.resolve({"path": path})["path"] == path
