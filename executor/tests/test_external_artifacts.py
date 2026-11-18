"""Mounted payload storage never moves SQLite, locks or Git worktrees."""

import json
from pathlib import Path

import pytest

from orcan_executor import cli, engine, retention, settings, storage, store, web


def submit(repo):
    return engine.submit(repo, "HEAD", "mounted", "quality", [], 30)


@pytest.fixture
def external(tmp_path, monkeypatch):
    root = tmp_path / "external"
    root.mkdir()
    monkeypatch.setenv("ORCAN_STORAGE_ROOT", str(root))
    monkeypatch.setenv("ORCAN_STORAGE_REQUIRE_MOUNT", "0")
    return root


def test_payloads_external_metadata_and_locks_local(repo, external, capsys):
    job = submit(repo)
    result = engine.run_job(job["id"])
    report = Path(result["report"])
    assert result["status"] == "passed"
    assert report.is_relative_to(external / "orcan/default/executor" / job["id"])
    assert (settings.state_dir() / "jobs" / job["id"] / "run.lock").exists()
    assert (settings.state_dir() / "jobs.sqlite").exists()
    assert not list(external.rglob("run.lock"))
    assert settings.worktree_root().is_relative_to(settings.state_dir())
    assert cli.main(["logs", job["id"], "--limit", "100"]) == 0
    assert json.loads(capsys.readouterr().out)["text"]
    assert cli.main(["artifacts", job["id"]]) == 0
    assert "report.json" in json.loads(capsys.readouterr().out)["artifacts"]
    from fastapi.testclient import TestClient

    client = TestClient(web.app)
    assert client.get("/api/jobs/" + job["id"] + "/report").status_code == 200
    assert client.get("/api/jobs/" + job["id"] + "/log").status_code == 200


def test_retention_removes_external_payload_only_and_preserves_other_data(repo, external):
    (external / "keep").write_text("user data")
    job = submit(repo)
    result = engine.run_job(job["id"])
    report = Path(result["report"])
    with store.database() as db:
        db.execute("UPDATE jobs SET finished='2000-01-01' WHERE id=?", (job["id"],))
    assert retention.prune(dry_run=True) == 1
    assert report.exists()
    assert retention.prune() == 1
    assert not report.parent.parent.exists()
    assert (external / "keep").read_text() == "user data"
    assert not (settings.state_dir() / "jobs" / job["id"]).exists()


def test_missing_mount_pauses_without_creating_fallback(repo, tmp_path, monkeypatch):
    missing = tmp_path / "missing"
    monkeypatch.setenv("ORCAN_STORAGE_ROOT", str(missing))
    monkeypatch.setenv("ORCAN_STORAGE_REQUIRE_MOUNT", "1")
    job = submit(repo)
    assert engine.run_job(job["id"]) is None
    assert store.get(job["id"])["attempts"] == 0
    assert not missing.exists()


def test_unmounted_existing_directory_is_not_used(repo, external, monkeypatch):
    monkeypatch.setenv("ORCAN_STORAGE_REQUIRE_MOUNT", "1")
    monkeypatch.setattr(Path, "is_mount", lambda self: False)
    job = submit(repo)
    assert engine.run_job(job["id"]) is None
    assert not (external / "orcan").exists()


def test_storage_write_failure_finishes_in_local_database(repo, external, monkeypatch):
    job = submit(repo)
    original = Path.write_text

    def write(path, *args, **kwargs):
        if path.name == "report.json" and path.is_relative_to(external):
            raise OSError("remote filesystem unavailable")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", write)
    result = engine.run_job(job["id"])
    assert result["status"] == "error"
    assert result["report"] is None
    assert "storage write failed" in result["summary"]["error"]
    assert store.get(job["id"])["status"] == "error"


def test_legacy_local_logs_readable_with_external_storage_unavailable(
    repo, tmp_path, monkeypatch, capsys
):
    job = submit(repo)
    assert engine.run_job(job["id"])["status"] == "passed"
    monkeypatch.setenv("ORCAN_STORAGE_ROOT", str(tmp_path / "missing"))
    assert cli.main(["logs", job["id"], "--limit", "100"]) == 0
    assert json.loads(capsys.readouterr().out)["text"]


def test_capacity_checks_payload_filesystem(repo, external, monkeypatch):
    from unittest.mock import Mock

    original = settings.artifact_root()

    def usage(path):
        return Mock(
            free=0 if Path(path).is_relative_to(external) else 2 * 1024**3, total=3 * 1024**3
        )

    monkeypatch.setattr(storage.shutil, "disk_usage", usage)
    assert not storage.capacity()["ready"]
    assert original.is_relative_to(external)
