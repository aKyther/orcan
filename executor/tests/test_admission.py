"""Real admission races, lane leases and capacity retries without a live broker."""

import fcntl
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import pytest
from celery.exceptions import Retry
from conftest import commit

from orcan_executor import cli, engine, readiness, settings, store, tasks


def test_running_limit_is_atomic_across_workers(repo, monkeypatch):
    monkeypatch.setenv("ORCAN_EXECUTOR_MAX_RUNNING", "2")
    jobs = [engine.submit(repo, "HEAD", "capacity", "quality", [], 30) for _ in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        admitted = list(pool.map(lambda job: store.start(job["id"], Path("fixture")), jobs))
    assert sum(admitted) == 2
    assert store.board()["counts"]["running"] == 2
    assert store.board()["counts"]["queued"] == 6
    waiting = next(job for job, started in zip(jobs, admitted, strict=True) if not started)
    assert engine.run_job(waiting["id"]) is None
    assert store.get(waiting["id"])["attempts"] == 0


def test_capacity_wait_is_retried_without_claiming_failure(monkeypatch):
    monkeypatch.setattr(tasks, "run_job", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks.store, "get", lambda _: {"status": "queued"})
    retry = Mock(side_effect=Retry())
    monkeypatch.setattr(tasks.verify, "retry", retry)
    with pytest.raises(Retry):
        tasks.verify.run("fixture")
    retry.assert_called_once_with(countdown=3, max_retries=None)


def test_lane_needs_both_lease_and_matching_process_lock(monkeypatch):
    monkeypatch.setenv("ORCAN_EXECUTOR_SPLIT_LANES", "1")
    monkeypatch.setattr(readiness.events, "client", lambda: Mock(get=lambda _: "1"))
    root = settings.state_dir()
    root.mkdir()
    with (root / "worker-heavy.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lanes = readiness.lanes()
        assert lanes["heavy"]["ready"]
        assert not lanes["light"]["ready"]
        monkeypatch.setattr(readiness.events, "client", lambda: Mock(get=lambda _: None))
        assert not readiness.lanes()["heavy"]["ready"]


def test_unavailable_lane_is_not_published_to_celery(repo, monkeypatch):
    job = engine.submit(repo, "HEAD", "missing-worker", "quality", [], 30)
    monkeypatch.setattr(readiness, "lanes", lambda: {"default": {"ready": False}})
    send = Mock()
    monkeypatch.setattr(tasks.verify, "apply_async", send)
    with pytest.raises(ValueError, match="lane default"):
        cli.enqueue(job["id"])
    send.assert_not_called()
    assert store.get(job["id"])["status"] == "queued"


def test_settings_are_bounded_and_show_effective_limits(monkeypatch):
    monkeypatch.setenv("ORCAN_EXECUTOR_TIMEOUT_SECONDS", "45")
    assert settings.effective()["timeout_seconds"] == 45
    monkeypatch.setenv("ORCAN_EXECUTOR_MAX_RUNNING", "4")
    with pytest.raises(ValueError, match="Running limit"):
        settings.effective()


def test_profile_timeout_and_explicit_override(repo, monkeypatch):
    config = repo / ".orcan/checks.json"
    value = json.loads(config.read_text())
    value["profiles"]["quality"]["timeout_seconds"] = 60
    value["profiles"]["quality"]["lane"] = "heavy"
    config.write_text(json.dumps(value))
    commit(repo)
    monkeypatch.setenv("ORCAN_EXECUTOR_TIMEOUT_SECONDS", "90")
    profile_job = engine.submit(repo, "HEAD", "profile", "quality", [], None)
    assert profile_job["timeout"] == 60 and profile_job["lane"] == "heavy"
    assert store.get(profile_job["id"])["lane"] == "heavy"
    assert engine.submit(repo, "HEAD", "explicit", "quality", [], 30)["timeout"] == 30


def test_cli_reports_local_queue_when_lane_is_missing(repo, monkeypatch, capsys):
    monkeypatch.setattr(readiness, "lanes", lambda: {"default": {"ready": False}})
    assert cli.main(["submit", "--repo", str(repo), "--profile", "quality"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "queued_locally"
    assert "lane default" in result["error"]
    assert store.get(result["job_id"])["status"] == "queued"
