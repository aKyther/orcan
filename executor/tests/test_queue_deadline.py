"""Queue deadlines and caller-visible failures work without Redis or Celery services."""

import fcntl
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from orcan_executor import (
    cli,
    diagnostics,
    engine,
    events,
    notifications,
    retention,
    settings,
    snapshots,
    store,
    tasks,
    web,
)


def waiting(repo, seconds):
    job = engine.submit(repo, "HEAD", "queue deadline", "quality", [], 30)
    since = (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat()
    with store.database() as db:
        db.execute("UPDATE jobs SET created=? WHERE id=?", (since, job["id"]))
    return job


@pytest.mark.parametrize("seconds,expired", [(1799, False), (1801, True), (7200, True)])
def test_queue_deadline_expires_without_broker_and_emits_one_terminal_result(
    repo, monkeypatch, seconds, expired
):
    job = waiting(repo, seconds)
    monkeypatch.setattr(events, "client", lambda: pytest.fail("No broker allowed"))
    assert engine.expire_queued_jobs() == int(expired)
    current = store.get(job["id"])
    assert current["status"] == ("timed_out" if expired else "queued")
    assert current["attempts"] == 0
    assert current["started"] is None
    assert current["worktree"] is None
    assert engine.expire_queued_jobs() == 0
    finished = [
        json.loads(e["payload"])
        for e in store.unpublished()
        if json.loads(e["payload"])["kind"] == "finished"
    ]
    assert len(finished) == int(expired)
    if expired:
        result = finished[0]
        assert result["sha"] == job["sha"]
        assert result["job_id"] == job["id"]
        assert result["summary"]["phase"] == "queue"
        assert result["summary"]["tests"] == 0
        assert result["summary"]["errors"] == 1
        report = TestClient(web.app).get(f"/api/jobs/{job['id']}/report")
        assert report.status_code == 200
        assert report.json()["status"] == "timed_out"


def test_late_delivery_cannot_run_or_retry_overdue_procedure(repo, monkeypatch):
    job = waiting(repo, 1801)
    monkeypatch.setattr(engine, "git", lambda *args: pytest.fail("Procedure must not start"))
    monkeypatch.setattr(tasks, "flush_events", lambda: None)
    retry = Mock()
    monkeypatch.setattr(tasks.verify, "retry", retry)
    tasks.verify.run(job["id"])
    tasks.verify.run(job["id"])
    retry.assert_not_called()
    assert store.get(job["id"])["status"] == "timed_out"
    assert store.get(job["id"])["attempts"] == 0


def test_queue_deadline_does_not_expire_running_procedure(repo):
    job = waiting(repo, 0)
    assert store.start(job["id"], Path("fixture"))
    with store.database() as db:
        db.execute("UPDATE jobs SET created='2000-01-01T00:00:00+00:00' WHERE id=?", (job["id"],))
    assert engine.expire_queued_jobs() == 0
    assert store.get(job["id"])["status"] == "running"


def test_held_execution_lock_prevents_queue_expiry(repo):
    job = waiting(repo, 1801)
    directory = settings.state_dir() / "jobs" / job["id"]
    directory.mkdir(parents=True)
    with (directory / "run.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert engine.expire_queued_jobs() == 0
        assert store.get(job["id"])["status"] == "queued"
    assert engine.expire_queued_jobs() == 1


def test_explicit_recovery_resets_queue_budget_but_not_snapshot_or_creation(repo):
    job = waiting(repo, 7200)
    before = store.get(job["id"])
    with engine.recovery_guard(job["id"]):
        pass  # Exercise local guarded recovery without publication.
    current = store.get(job["id"])
    assert current["created"] == before["created"]
    assert current["sha"] == before["sha"]
    assert current["queued_since"] > before["created"]
    assert engine.expire_queued_jobs() == 0
    assert engine.run_job(job["id"])["status"] == "passed"


def test_timeout_reaches_registered_caller_as_error_without_running_tests(repo, monkeypatch):
    job = waiting(repo, 1801)
    notifications.register(job["id"], str(uuid4()))
    assert engine.expire_queued_jobs() == 1
    invoke = Mock(return_value=("queued", "fixture transport"))
    monkeypatch.setattr(notifications, "_invoke", invoke)
    assert notifications.deliver(job["id"]) == 1
    message = notifications.message(store.get(job["id"]))
    assert '"status":"timed_out"' in message
    assert "Queue wait exceeded 30 minutes" in message
    assert '"tests":0' in message
    assert "--artifact report.json" in message
    invoke.assert_called_once()
    with pytest.raises(ValueError, match="Completed"):
        with engine.recovery_guard(job["id"]):
            pytest.fail("Timeout must not be revived implicitly")


def test_stalled_queue_warns_even_when_redis_and_workers_are_ready(repo, monkeypatch):
    waiting(repo, 300)
    connection = Mock()
    connection.info.return_value = {"aof_enabled": 1, "aof_last_write_status": "ok"}
    monkeypatch.setattr(events, "client", lambda: connection)
    monkeypatch.setattr(
        diagnostics, "lanes", lambda: {"default": {"configured": True, "ready": True}}
    )
    sample = diagnostics.sample()
    assert sample["status"] == "online"
    assert "queue_stalled" in sample["warnings"]


def test_recent_execution_activity_suppresses_stalled_warning(repo):
    old = waiting(repo, 300)
    recent = waiting(repo, 0)
    store.finish(recent["id"], "passed", {}, None)
    assert not diagnostics.jobs()["stalled"]
    assert store.get(old["id"])["status"] == "queued"


def test_concurrent_deadline_sweeps_emit_exactly_one_failure(repo):
    job = waiting(repo, 1801)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: engine.expire_queued_jobs(), range(4)))
    assert sum(results) == 1
    finished = [
        json.loads(event["payload"])
        for event in store.unpublished()
        if json.loads(event["payload"])["kind"] == "finished"
    ]
    assert len(finished) == 1
    assert finished[0]["job_id"] == job["id"]


def test_unverifiable_execution_lock_preserves_job_and_logs_error(repo, monkeypatch, caplog):
    job = waiting(repo, 1801)

    def unreadable(*args):
        raise PermissionError("fixture lock unavailable")

    monkeypatch.setattr(engine.fcntl, "flock", unreadable)
    assert engine.expire_queued_jobs() == 0
    assert store.get(job["id"])["status"] == "queued"
    assert "state preserved" in caplog.text


def test_maintenance_records_timeout_during_broker_outage(repo, monkeypatch):
    job = waiting(repo, 1801)
    monkeypatch.setattr(snapshots, "prune_snapshots", lambda: None)
    monkeypatch.setattr(
        diagnostics, "sample", lambda: {"sampled_at": store.now(), "status": "offline"}
    )

    def unavailable():
        raise ConnectionError("fixture broker offline")

    def end_tick(*args):
        raise RuntimeError("maintenance tick completed")

    monkeypatch.setattr(events, "publish_pending", unavailable)
    monkeypatch.setattr(retention.time, "sleep", end_tick)
    with pytest.raises(RuntimeError, match="tick completed"):
        retention.maintain()
    assert store.get(job["id"])["status"] == "timed_out"
    assert any(json.loads(e["payload"]).get("status") == "timed_out" for e in store.unpublished())


@pytest.mark.parametrize("command", ["result", "wait"])
def test_queue_timeout_returns_nonzero_to_shell_caller_without_broker(
    repo, monkeypatch, capsys, command
):
    job = waiting(repo, 1801)
    assert engine.expire_queued_jobs() == 1
    monkeypatch.setattr(events, "client", lambda: pytest.fail("Local failure needs no broker"))
    assert cli.main([command, job["id"]]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "timed_out"
    assert result["summary"]["phase"] == "queue"


def test_wait_returns_nonzero_when_queue_timeout_arrives_on_stream(repo, monkeypatch, capsys):
    job = waiting(repo, 0)
    connection = Mock()
    connection.xrevrange.return_value = []
    monkeypatch.setattr(events, "client", lambda: connection)

    def timeout_after_subscription(*args):
        with store.database() as db:
            db.execute(
                "UPDATE jobs SET created='2000-01-01T00:00:00+00:00' WHERE id=?", (job["id"],)
            )
        assert engine.expire_queued_jobs() == 1
        return iter([json.loads(store.unpublished()[-1]["payload"])])

    monkeypatch.setattr(events, "listen", timeout_after_subscription)
    assert cli.main(["wait", job["id"], "--timeout", "1"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "timed_out"
