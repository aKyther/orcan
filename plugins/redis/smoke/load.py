"""Finite real Redis/Celery stress and resilience checks inside the isolated fixture.

Full measurements go to a local JSON artifact. No live Orcan state is used.
"""

import contextlib
import io
import json
import os
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from orcan_executor import cli, engine, events, retention, store
from orcan_executor.metrics import model_result, wire
from orcan_executor.tasks import verify


def control(*args):
    root = os.environ["ORCAN_SUPERVISOR_STATE_D"]
    subprocess.run(
        ["supervisorctl", "-c", root + "/supervisord.conf", *args], check=True, capture_output=True
    )


def deliver(repo, index):
    selector = "test_example.py::test_fails" if index % 5 == 0 else "test_example.py::test_passes"
    job = engine.submit(repo, "HEAD", f"burst-{index}", "pytest", [selector], 60)
    verify.apply_async(args=[job["id"]], task_id=job["id"])
    if index % 5 == 1:
        # Late or duplicate queue deliveries must not execute another attempt.
        verify.apply_async(args=[job["id"]], task_id=job["id"])
    return job


def collect(jobs, timeout=150):
    ids = {job["id"] for job in jobs}
    completed = {}
    seen_events = set()
    active = set()
    maximum_active = 0
    cursor = "0-0"
    reconnected = False
    connection = events.client()
    deadline = time.monotonic() + timeout
    while len(completed) < len(ids):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(f"Burst deadline: {len(completed)}/{len(ids)} completed")
        batches = connection.xread(
            {events.stream_name(): cursor},
            count=100,
            block=min(3000, max(1, int(remaining * 1000))),
        )
        reconnect = False
        for _, messages in batches:
            for cursor, fields in messages:
                payload = json.loads(fields["payload"])
                if payload.get("job_id") not in ids or payload["event_id"] in seen_events:
                    continue
                seen_events.add(payload["event_id"])
                if payload.get("kind") == "running":
                    active.add(payload["job_id"])
                    maximum_active = max(maximum_active, len(active))
                if payload.get("kind") == "finished":
                    active.discard(payload["job_id"])
                    assert payload["job_id"] not in completed
                    result = model_result(payload)
                    assert (
                        len(wire(result).encode()) + 1
                        == payload["summary"]["metrics"]["result_bytes"]
                    )
                    assert len(wire(result).encode()) < 3000
                    assert "metrics" not in result["summary"]
                    assert "successful pytest noise" not in wire(result)
                    completed[payload["job_id"]] = payload
                    if len(completed) == 25 and not reconnected:
                        reconnected = reconnect = True
                        break
            if reconnect:
                break
        if reconnect:
            connection.close()
            connection = events.client()
    connection.close()
    assert maximum_active == 1, maximum_active
    assert not active
    assert reconnected
    return completed


def main(repo):
    began = time.monotonic()
    # Multiple real submitters share Git, SQLite and Celery's broker connection pool.
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = list(pool.map(lambda index: deliver(repo, index), range(50)))
    assert len({job["id"] for job in jobs}) == 50
    assert len(collect(jobs)) == 50
    rows = [store.get(job["id"]) for job in jobs]
    assert all(row["attempts"] == 1 for row in rows)
    assert all(row["sha"] == job["sha"] for row, job in zip(rows, jobs, strict=True))
    assert all(not Path(row["worktree"]).exists() for row in rows)
    passed = sum(row["status"] == "passed" for row in rows)
    failed = sum(row["status"] == "failed" for row in rows)
    assert (passed, failed) == (40, 10)
    assert (repo / "marker").read_text() == "agent editing"
    full_bytes = sum(row["summary"]["metrics"]["log_bytes"] for row in rows)
    result_bytes = sum(row["summary"]["metrics"]["result_bytes"] for row in rows)
    assert full_bytes > result_bytes

    # Gracefully stop the idle worker. A newly queued job survives the stop
    # and runs after start, without another attempt.
    control("stop", "executor-worker")
    queued = engine.submit(
        repo, "HEAD", "worker-restart", "pytest", ["test_example.py::test_passes"], 60
    )
    verify.apply_async(args=[queued["id"]], task_id=queued["id"])
    assert store.get(queued["id"])["status"] == "queued"
    control("start", "executor-worker")
    event = next(events.listen("0-0", queued["id"], timeout=30))
    assert event["status"] == "passed" and store.get(queued["id"])["attempts"] == 1

    # Broker down: a submission stays durable and explicit recovery delivers it.
    control("stop", "executor-redis")
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = cli.main(
            [
                "submit",
                "--repo",
                str(repo),
                "--profile",
                "pytest",
                "--test",
                "test_example.py::test_passes",
            ]
        )
    offline = json.loads(output.getvalue())
    assert code == 2 and offline["status"] == "queued_locally"
    assert store.get(offline["job_id"])["status"] == "queued"
    control("start", "executor-redis")
    deadline = time.monotonic() + 30
    while True:
        try:
            events.client().ping()
            break
        except Exception:
            if time.monotonic() >= deadline:
                raise AssertionError("Broker restart deadline exceeded") from None
            time.sleep(0.2)
    with contextlib.redirect_stdout(io.StringIO()):
        assert cli.main(["recover", "--job", offline["job_id"]]) == 0
    event = next(events.listen("0-0", offline["job_id"], timeout=30))
    assert event["status"] == "passed"

    # Replay is at least once. Existing event IDs allow deduplication and stored
    # jobs are not executed again. The original terminal event remains stable.
    events.publish_pending(replay=True)
    assert all(store.get(job["id"])["attempts"] == 1 for job in jobs)

    # Accelerate the completed deadline in this fixture only; the cleanup must
    # remove artifacts, rows and pins, and must not touch another queued job.
    preserved = engine.submit(
        repo, "HEAD", "preserve-queued", "pytest", ["test_example.py::test_passes"], 60
    )
    with store.database() as db:
        db.executemany(
            "UPDATE jobs SET finished='2000-01-01' WHERE id=?", [(job["id"],) for job in jobs]
        )
    assert retention.prune() == 50
    assert store.get(preserved["id"])["status"] == "queued"
    assert all(
        not (Path(os.environ["ORCAN_EXECUTOR_STATE_DIR"]) / "jobs" / job["id"]).exists()
        for job in jobs
    )
    for job in jobs:
        assert engine.git(repo, "for-each-ref", "refs/orcan/executor/jobs/" + job["id"]) == ""
    # Drain the fixture-only preserved job so no queued work is abandoned.
    verify.apply_async(args=[preserved["id"]], task_id=preserved["id"])
    assert next(events.listen("0-0", preserved["id"], timeout=30))["status"] == "passed"
    elapsed = round(time.monotonic() - began, 3)
    queue_times = sorted(row["summary"]["metrics"]["queue_seconds"] for row in rows)
    report = {
        "jobs": 50,
        "passed": passed,
        "failed": failed,
        "submitters": 8,
        "duplicate_deliveries": 10,
        "max_simultaneous_jobs": 1,
        "attempts_per_job": 1,
        "consumer_reconnected_after": 25,
        "log_bytes": full_bytes,
        "model_result_bytes": result_bytes,
        "reduction_percent": round(100 * (full_bytes - result_bytes) / full_bytes, 2),
        "elapsed_seconds": elapsed,
        "mean_queue_seconds": round(statistics.mean(queue_times), 3),
        "p95_queue_seconds": queue_times[47],
        "graceful_worker_restart": True,
        "broker_outage_recovery": True,
        "ttl_removed_jobs": 50,
        "snapshot_preserved": True,
    }
    Path(os.environ["ORCAN_EXECUTOR_STATE_DIR"]).joinpath("load-report.json").write_text(
        json.dumps(report, indent=2)
    )
    print(json.dumps(report))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
