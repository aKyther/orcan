import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import pytest
from conftest import commit

from orcan_executor import cli, engine, profiles, retention, store


def submit(repo, *, reuse=False):
    return engine.submit(repo, "HEAD", "controls", "selected", ["Test"], 30, reuse=reuse)


def test_fifty_job_capacity_is_atomic_and_rejection_leaves_no_pins(repo, monkeypatch):
    monkeypatch.setenv("ORCAN_EXECUTOR_MAX_PENDING", "50")

    def producer(_):
        try:
            return submit(repo)["id"]
        except ValueError as error:
            assert "capacity" in str(error)
            return None

    with ThreadPoolExecutor(max_workers=8) as workers:
        accepted = list(workers.map(producer, range(60)))
    assert sum(value is not None for value in accepted) == 50
    assert len(store.listing()) == 50
    assert len(engine.git(repo, "for-each-ref", "refs/orcan/executor/jobs").splitlines()) == 50


def test_reuse_is_atomic_and_keeps_one_pinned_job(repo):
    with ThreadPoolExecutor(max_workers=8) as workers:
        ids = list(workers.map(lambda _: submit(repo, reuse=True)["id"], range(20)))
    assert len(set(ids)) == 1
    assert len(store.listing()) == 1
    assert len(engine.git(repo, "for-each-ref", "refs/orcan/executor/jobs").splitlines()) == 1


def test_cancelled_work_never_executes_and_releases_capacity(repo, monkeypatch):
    monkeypatch.setenv("ORCAN_EXECUTOR_MAX_PENDING", "1")
    job = submit(repo)
    result = engine.cancel(job["id"])
    assert result["status"] == "cancelled"
    assert engine.run_job(job["id"]) is None
    assert submit(repo)["id"] != job["id"]
    with pytest.raises(ValueError, match="queued"):
        engine.cancel(job["id"])


def test_cancel_does_not_interrupt_a_running_job(repo):
    import fcntl

    job = submit(repo)
    directory = Path(store.state_dir()) / "jobs" / job["id"]
    directory.mkdir(parents=True)
    with (directory / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="running"):
            engine.cancel(job["id"])
    assert store.get(job["id"])["status"] == "queued"


def test_ack_is_explicit_idempotent_and_detail_metrics_are_separate(repo):
    job = submit(repo)
    with pytest.raises(ValueError, match="completed"):
        store.acknowledge(job["id"])
    engine.run_job(job["id"])
    assert store.board()["stats"]["acknowledged_jobs"] == 0
    store.acknowledge(job["id"])
    store.acknowledge(job["id"])
    store.detail_read(job["id"], 4000)
    stats = store.board()["stats"]
    assert stats["acknowledged_jobs"] == 1
    assert stats["detail_reads"] == 1
    assert stats["detail_bytes"] == 4000
    assert stats["by_status"][0]["status"] == "passed"
    assert stats["by_status"][0]["log_bytes"] > stats["by_status"][0]["result_bytes"]


def test_profile_lane_routes_work_without_changing_global_queue(repo, monkeypatch):
    from orcan_executor.tasks import verify

    config = json.loads((repo / profiles.CONFIG).read_text())
    config["profiles"]["selected"]["lane"] = "heavy"
    (repo / profiles.CONFIG).write_text(json.dumps(config))
    commit(repo)
    job = submit(repo)
    send = Mock()
    monkeypatch.setattr(verify, "apply_async", send)
    cli.enqueue(job["id"])
    assert send.call_args.kwargs["queue"].endswith(":heavy")
    assert send.call_args.kwargs["task_id"] == job["id"]


def test_invalid_lane_rejected_before_submission(repo):
    config = json.loads((repo / profiles.CONFIG).read_text())
    config["profiles"]["selected"]["lane"] = "remote"
    with pytest.raises(ValueError, match="lane"):
        profiles.load(json.dumps(config))


def test_repeated_worker_interruptions_are_bounded(repo):
    job = submit(repo)
    with store.database() as db:
        db.execute("UPDATE jobs SET attempts=3, status='running' WHERE id=?", (job["id"],))
    result = engine.run_job(job["id"])
    assert result["status"] == "error"
    assert "interrupted" in result["summary"]["error"]
    assert engine.run_job(job["id"]) is None


def test_cancelled_results_follow_completed_ttl(repo):
    job = submit(repo)
    engine.cancel(job["id"])
    with store.database() as db:
        db.execute("UPDATE jobs SET finished='2000-01-01T00:00:00+00:00' WHERE id=?", (job["id"],))
    assert retention.prune() == 1
    assert store.listing() == []
    assert engine.git(repo, "for-each-ref", "refs/orcan/executor/jobs") == ""
