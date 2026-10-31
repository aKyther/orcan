"""Compact history survives artifact TTL without retaining diagnostic text."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from orcan_executor import cli, engine, notifications, retention, store, web


def age(job_id, hours):
    finished = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    with store.database() as db:
        db.execute("UPDATE jobs SET finished=? WHERE id=?", (finished, job_id))


def completed(repo):
    # A reviewed profile without test selectors can do ordinary heavy work too.
    job = engine.submit(repo, "HEAD", "compile-report", "quality", [], 30)
    result = engine.run_job(job["id"])
    assert result["status"] == "passed"
    assert result["summary"]["tests"] == 0
    return job


def test_expiry_preserves_history_measurements_and_delivery(repo, monkeypatch, capsys):
    job = completed(repo)
    thread = str(uuid4())
    notifications.register(job["id"], thread)
    monkeypatch.setattr(notifications, "_invoke", lambda *args: ("queued", "fixture"))
    assert notifications.deliver(job["id"]) == 1
    store.acknowledge(job["id"])
    age(job["id"], 2)
    with store.database() as db:
        row = store.get(job["id"])
        summary = row["summary"] | {"log_tail": "PRIVATE DIAGNOSTIC", "error": "PRIVATE ERROR"}
        db.execute("UPDATE jobs SET summary=? WHERE id=?", (json.dumps(summary), job["id"]))
    before = store.board(3)
    report = Path(store.get(job["id"])["report"])
    assert retention.prune() == 1
    after = store.board(3)
    assert after["stats"] == before["stats"]
    assert after["coverage"] == before["coverage"]
    assert after["notification_stats"] == before["notification_stats"]
    assert after["delivery_counts"] == before["delivery_counts"]
    assert after["counts"]["passed"] == 1
    archived = store.get(job["id"])
    assert archived["details_expired"] == 1
    assert archived["report"] is None and archived["worktree"] is None
    assert not report.exists()
    assert "PRIVATE" not in json.dumps(archived)
    assert archived["selectors"] == []
    assert retention.prune() == 0  # Repeated cleanup never counts the job twice.
    assert notifications.deliver(job["id"]) == 0
    with pytest.raises(ValueError):
        notifications.register(job["id"], str(uuid4()))
    client = TestClient(web.app)
    assert client.get(f"/api/jobs/{job['id']}/report").status_code == 404
    assert client.get("/api/board?hours=3").json()["jobs"][0]["details_expired"] == 1
    assert cli.main(["history", "--hours", "3"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["jobs"][0]["id"] == job["id"]
    assert result["jobs"][0]["seconds"] >= 0


def test_windows_use_completion_time_and_keep_active_jobs(repo):
    job = completed(repo)
    age(job["id"], 4)
    active = engine.submit(repo, "HEAD", "still-queued", "quality", [], 30)
    with store.database() as db:
        db.execute("UPDATE jobs SET created='2000-01-01' WHERE id=?", (active["id"],))
    assert retention.prune() == 1
    recent = store.board(3)
    assert recent["stats"]["completed_jobs"] == 0
    assert recent["counts"]["queued"] == 1
    assert [row["id"] for row in recent["jobs"]] == [active["id"]]
    assert store.board(24)["stats"]["completed_jobs"] == 1
    assert TestClient(web.app).get("/api/board?hours=0").status_code == 422
    with pytest.raises(ValueError):
        store.board(721)


def test_history_age_and_count_limits_preserve_active_jobs(repo, monkeypatch):
    jobs = [completed(repo) for _ in range(3)]
    active = engine.submit(repo, "HEAD", "active", "quality", [], 30)
    for index, job in enumerate(jobs):
        age(job["id"], 2 + index)
    monkeypatch.setattr(retention, "HISTORY_LIMIT", 2)
    assert retention.prune() == 3
    with pytest.raises(ValueError):
        store.get(jobs[-1]["id"])
    assert store.get(active["id"])["status"] == "queued"
    age(jobs[0]["id"], 31 * 24)
    assert retention.prune() == 0
    with pytest.raises(ValueError):
        store.get(jobs[0]["id"])
    assert store.get(jobs[1]["id"])["details_expired"] == 1
