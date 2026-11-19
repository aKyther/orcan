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


@pytest.mark.parametrize("limit", [1, 2, 3, 4, 5])
def test_running_limit_is_atomic_across_workers(repo, monkeypatch, limit):
    monkeypatch.setenv("ORCAN_EXECUTOR_MAX_RUNNING", str(limit))
    jobs = [engine.submit(repo, "HEAD", "capacity", "quality", [], 30) for _ in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        admitted = list(pool.map(lambda job: store.start(job["id"], Path("fixture")), jobs))
    assert sum(admitted) == limit
    assert store.board()["counts"]["running"] == limit
    assert store.board()["counts"]["queued"] == 8 - limit
    waiting = next(job for job, started in zip(jobs, admitted, strict=True) if not started)
    assert engine.run_job(waiting["id"]) is None
    assert store.get(waiting["id"])["attempts"] == 0


def test_capacity_wait_is_retried_without_claiming_failure(monkeypatch):
    monkeypatch.setattr(tasks.random, "uniform", lambda low, high: high)
    monkeypatch.setattr(tasks, "run_job", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks.store, "get", lambda _: {"status": "queued"})
    retry = Mock(side_effect=Retry())
    monkeypatch.setattr(tasks.verify, "retry", retry)
    with pytest.raises(Retry):
        tasks.verify.run("fixture")
    retry.assert_called_once_with(countdown=3)


@pytest.mark.parametrize("retries", [0, 3, 10, 100])
def test_real_celery_retry_survives_extended_admission_wait(repo, monkeypatch, caplog, retries):
    monkeypatch.setenv("ORCAN_EXECUTOR_MAX_RUNNING", "1")
    first = engine.submit(repo, "HEAD", "occupying", "quality", [], 30)
    waiting = engine.submit(repo, "HEAD", "waiting", "quality", [], 30)
    assert store.start(first["id"], Path("fixture"))
    # Exercise Celery's real retry implementation; intercept only publication.
    send = Mock()
    monkeypatch.setattr(tasks.verify, "apply_async", send)
    tasks.verify.push_request(
        id=waiting["id"],
        args=(waiting["id"],),
        kwargs={},
        retries=retries,
        called_directly=False,
        is_eager=False,
    )
    try:
        with pytest.raises(Retry):
            tasks.verify.run(waiting["id"])
    finally:
        tasks.verify.pop_request()
    send.assert_called_once()
    assert send.call_args.kwargs["retries"] == retries + 1
    ceiling = min(60, 3 * 2 ** min(retries, 5))
    assert ceiling / 2 <= send.call_args.kwargs["countdown"] <= ceiling
    assert "awaiting admission (capacity)" in caplog.text
    assert store.get(waiting["id"])["status"] == "queued"
    assert store.get(waiting["id"])["attempts"] == 0
    store.finish(first["id"], "cancelled", {}, None)
    monkeypatch.setattr(tasks, "flush_events", lambda: None)
    tasks.verify.run(waiting["id"])
    assert store.get(waiting["id"])["status"] == "passed"
    assert store.get(waiting["id"])["attempts"] == 1
    assert send.call_count == 1


def test_fair_turn_wait_survives_retry_budget_until_missing_delivery_is_bypassed(repo, monkeypatch):
    preferred = engine.submit(repo, "HEAD", "preferred", "quality", [], 30)
    store.publication(preferred["id"], "published")
    waiting = engine.submit(repo, "HEAD", "waiting", "quality", [], 30)
    send = Mock()
    monkeypatch.setattr(tasks.verify, "apply_async", send)
    tasks.verify.push_request(
        id=waiting["id"],
        args=(waiting["id"],),
        kwargs={},
        retries=10,
        called_directly=False,
        is_eager=False,
    )
    try:
        with pytest.raises(Retry):
            tasks.verify.run(waiting["id"])
    finally:
        tasks.verify.pop_request()
    assert store.get(waiting["id"])["admission_reason"] == "fair_turn"
    assert store.get(waiting["id"])["attempts"] == 0
    with store.database() as db:
        db.execute(
            "UPDATE jobs SET fair_wait_started='2000-01-01T00:00:00+00:00' WHERE id=?",
            (waiting["id"],),
        )
    monkeypatch.setattr(tasks, "flush_events", lambda: None)
    tasks.verify.run(waiting["id"])
    assert store.get(waiting["id"])["status"] == "passed"
    assert store.get(waiting["id"])["fairness_bypasses"] == 1
    assert store.get(preferred["id"])["status"] == "queued"
    assert store.get(preferred["id"])["attempts"] == 0
    assert send.call_count == 1


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
    monkeypatch.setenv("ORCAN_EXECUTOR_MAX_RUNNING", "11")
    with pytest.raises(ValueError, match="Running limit"):
        settings.effective()


@pytest.mark.parametrize("status", ["passed", "failed", "error", "timed_out", "cancelled"])
def test_terminal_delivery_never_retries_procedure(monkeypatch, status):
    monkeypatch.setattr(tasks, "run_job", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks.store, "get", lambda _: {"status": status})
    monkeypatch.setattr(tasks, "flush_events", lambda: None)
    retry = Mock()
    monkeypatch.setattr(tasks.verify, "retry", retry)
    tasks.verify.run("fixture")
    retry.assert_not_called()


def test_profile_timeout_and_explicit_override(repo, monkeypatch):
    monkeypatch.setenv("ORCAN_EXECUTOR_SPLIT_LANES", "1")
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
