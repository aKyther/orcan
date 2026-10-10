"""Target registration, clone mismatch and replacement preserve user data."""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from ._scripts_loader import load_script

pytestmark = pytest.mark.integration

target = load_script("studio-target.py")


def config(root: Path, name="tester") -> Path:
    path = root / "instances" / name / "orcan.config.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"workspaces": [], "identity": {"name": "Kept snapshot"}})
    )
    return path


def test_probe_never_initializes_and_concurrent_registration_is_stable(tmp_path):
    cfg = config(tmp_path)
    original = cfg.read_bytes()
    assert target.snapshot(tmp_path, cfg)["state"] == "unregistered"
    assert cfg.read_bytes() == original
    assert not (tmp_path / "studio-host.json").exists()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: target.register(tmp_path, cfg), range(4)))
    assert all(item == results[0] for item in results)
    assert results[0]["state"] == "ready"
    assert json.loads(cfg.read_text())["identity"]["name"] == "Kept snapshot"


def test_hosts_and_containers_have_separate_ids_and_label_changes_preserve_them(
    tmp_path,
):
    first = config(tmp_path, "first")
    second = config(tmp_path, "second")
    a = target.register(tmp_path, first)
    b = target.register(tmp_path, second)
    assert a["host_id"] == b["host_id"]
    assert a["container_id"] != b["container_id"]
    renamed = tmp_path / "instances" / "renamed"
    first.parent.rename(renamed)
    assert target.snapshot(tmp_path, renamed / first.name) == a


def test_clone_requires_explicit_host_and_container_rekeying(tmp_path, monkeypatch):
    cfg = config(tmp_path)
    first = target.register(tmp_path, cfg)
    monkeypatch.setattr(target, "fingerprint", lambda: "new-machine")
    assert target.snapshot(tmp_path, cfg)["state"] == "mismatch"
    with pytest.raises(ValueError, match="fingerprint"):
        target.register(tmp_path, cfg)
    target.write(
        tmp_path / "studio-host.json",
        {"id": "4efec8b2-d27b-4b10-8611-03f4347414fb", "fingerprint": "new-machine"},
    )
    with pytest.raises(ValueError, match="cloned"):
        target.register(tmp_path, cfg)
    cloned = target.register(tmp_path, cfg, new_target=True)
    assert cloned["container_id"] != first["container_id"]
    assert cloned["host_id"] != first["host_id"]


def docker_result(monkeypatch, *, exists=False, available=True):
    def run(args, **kwargs):
        if args[1] == "inspect":
            return subprocess.CompletedProcess(
                args,
                0 if exists else 1,
                stdout="sha256:container" if exists else "",
                stderr="",
            )
        if not available:
            raise subprocess.CalledProcessError(1, args)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(target.subprocess, "run", run)


def test_replacement_archives_only_named_instance_and_allocates_new_id(
    tmp_path, monkeypatch
):
    cfg = config(tmp_path)
    sibling = config(tmp_path, "sibling")
    registered = target.register(tmp_path, cfg)
    metadata = cfg.parent / "workspaces" / "review" / ".orcan"
    metadata.mkdir(parents=True)
    (metadata / "session-brief.md").write_text("Keep handoff")
    source = tmp_path / "sandbox" / "repo"
    source.mkdir(parents=True)
    (source / "work.txt").write_text("Keep project")
    docker_result(monkeypatch)
    plan = target.retire(
        tmp_path, cfg, "orcan-tester", registered["container_id"], False
    )
    assert cfg.exists() and not Path(plan["archive"]).exists()
    target.retire(tmp_path, cfg, "orcan-tester", registered["container_id"], True)
    archived = Path(plan["archive"])
    assert not cfg.exists() and sibling.exists()
    assert (
        archived / "workspaces/review/.orcan/session-brief.md"
    ).read_text() == "Keep handoff"
    assert (source / "work.txt").read_text() == "Keep project"
    replacement = config(tmp_path)
    new = target.register(tmp_path, replacement)
    assert new["host_id"] == registered["host_id"]
    assert new["container_id"] != registered["container_id"]


@pytest.mark.parametrize("exists,available", [(True, True), (False, False)])
def test_replacement_refuses_live_container_or_unavailable_docker(
    tmp_path, monkeypatch, exists, available
):
    cfg = config(tmp_path)
    registered = target.register(tmp_path, cfg)
    docker_result(monkeypatch, exists=exists, available=available)
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        target.retire(tmp_path, cfg, "orcan-tester", registered["container_id"], True)
    assert cfg.exists()


def test_replacement_refuses_projects_inside_instance_directory(tmp_path, monkeypatch):
    cfg = config(tmp_path)
    registered = target.register(tmp_path, cfg)
    data = json.loads(cfg.read_text())
    data["workspaces"] = [{"projects": [{"path": str(cfg.parent / "my-project")}]}]
    cfg.write_text(json.dumps(data))
    docker_result(monkeypatch)
    with pytest.raises(ValueError, match="project lives"):
        target.retire(tmp_path, cfg, "orcan-tester", registered["container_id"], True)
    assert cfg.exists()
