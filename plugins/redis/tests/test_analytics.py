"""Measured history aggregations and local chart assets."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from orcan_executor import engine, store, web


def test_timeline_and_profile_usage_match_measured_totals(repo):
    job = engine.submit(repo, "HEAD", "build", "quality", [], 30)
    engine.run_job(job["id"])
    store.detail_read(job["id"], 100, 180)
    board = store.board(3)
    bucket = next(row for row in board["timeline"] if row["jobs"])
    stats = board["stats"]
    assert bucket["jobs"] == bucket["passed"] == 1
    assert bucket["log_bytes"] == stats["log_bytes"]
    assert (
        bucket["result_bytes"] + bucket["detail_wire_bytes"] == stats["return_with_details_bytes"]
    )
    assert stats["reduction_with_details_bytes"] == stats["log_bytes"] - stats["result_bytes"] - 180
    assert stats["child_cpu_seconds"] >= 0
    assert stats["queue_p50_seconds"] == stats["queue_p95_seconds"] == bucket["queue_seconds"]
    assert board["profile_usage"][0]["profile"] == "quality"
    assert board["timeline_bucket_seconds"] == 300
    assert store.board(720)["timeline_bucket_seconds"] == 86400


def test_chart_assets_are_local_and_have_accessible_data_table():
    client = TestClient(web.app)
    page = client.get("/").text
    asset = client.get("/assets/charts.js")
    assert asset.status_code == 200
    assert "getContext('2d')" in asset.text
    assert 'id="timeline-rows"' in page
    assert 'src="assets/charts.js"' in page
    assert "cdn." not in page


def insert_sample(identifier, finished, summary=None, status="passed", source="recorded"):
    with store.database() as db:
        db.execute(
            "INSERT INTO jobs(id,repo,sha,task,profile,selectors,timeout,status,created,finished,summary,history_source) "
            "VALUES(?, '/fixture', ?, ?, 'fixture', '[]', 30, ?, ?, ?, ?, ?)",
            (
                identifier,
                "a" * 40,
                identifier,
                status,
                finished,
                finished,
                json.dumps(summary) if summary is not None else None,
                source,
            ),
        )


@pytest.mark.parametrize("hours,interval", [(3, 300), (24, 3600), (168, 21600), (720, 86400)])
def test_many_jobs_gaps_cancellations_and_partial_measurements(hours, interval):
    stamp = datetime.now(UTC) - timedelta(minutes=20)
    for i in range(120):
        insert_sample(
            str(i),
            stamp.isoformat(),
            dict(tests=2, seconds=i, metrics=dict(log_bytes=100, result_bytes=10, queue_seconds=i)),
        )
    insert_sample("cancelled", stamp.isoformat(), status="cancelled")
    insert_sample(
        "recovered",
        stamp.isoformat(),
        dict(tests=3, seconds=0, metrics=dict(log_bytes=0, result_bytes=0)),
        source="recovered",
    )
    insert_sample("outside", (stamp - timedelta(hours=hours + 1)).isoformat(), dict(tests=999))
    board = store.board(hours)
    assert len(board["jobs"]) == 100  # List cap does not cap statistics or charts.
    assert board["stats"]["completed_jobs"] == 122
    assert board["stats"]["measured_result_jobs"] == 121
    assert board["stats"]["tests"] == 243
    assert board["stats"]["queue_p95_seconds"] == 113
    assert board["coverage"]["completed_jobs"] == 122
    assert board["coverage"]["recovered_jobs"] == 1
    assert board["coverage"]["return_jobs"] == 120
    assert sum(row["jobs"] for row in board["timeline"]) == 122
    assert sum(row["cancelled"] for row in board["timeline"]) == 1
    assert sum(row["problems"] for row in board["timeline"]) == 0
    assert sum(row["log_bytes"] or 0 for row in board["timeline"]) == 12000
    assert sum(row["returned_bytes"] or 0 for row in board["timeline"]) == 1200
    occupied = next(row for row in board["timeline"] if row["jobs"])
    assert occupied["queue_p95_seconds"] == 113
    assert occupied["queue_jobs"] == 120
    assert occupied["run_jobs"] == 121
    assert all(
        b["bucket"] - a["bucket"] == interval
        for a, b in zip(board["timeline"], board["timeline"][1:])
    )
    assert all(row["queue_seconds"] is None for row in board["timeline"] if not row["jobs"])


def test_missing_values_are_not_measured_zeros_or_unpaired_savings():
    stamp = datetime.now(UTC).isoformat()
    insert_sample("missing", stamp)
    insert_sample("log-only", stamp, dict(metrics=dict(log_bytes=900)))
    board = store.board(3)
    row = next(row for row in board["timeline"] if row["jobs"])
    assert row["result_bytes"] is None
    assert row["returned_bytes"] is None
    assert row["queue_seconds"] is None
    assert row["run_seconds"] is None
    assert board["coverage"]["compared_jobs"] == 0
    assert board["stats"]["reduction_percent"] is None
    assert board["stats"]["reduction_bytes"] == 0
    assert board["stats"]["completed_jobs"] == 2


def test_board_uses_one_snapshot_when_job_changes_during_read(monkeypatch):
    stamp = datetime.now(UTC).isoformat()
    insert_sample(
        "changing", stamp, dict(tests=1, seconds=1, metrics=dict(log_bytes=10, result_bytes=2))
    )
    with store.database() as db:
        db.execute("PRAGMA journal_mode=WAL")
        path = db.execute("PRAGMA database_list").fetchone()[2]
    original = store.database
    changed = False

    class ConcurrentWrite:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, sql, *args):
            nonlocal changed
            cursor = self.connection.execute(sql, *args)
            if "SELECT * FROM scoped_jobs ORDER BY" in sql and not changed:
                with sqlite3.connect(path) as writer:
                    writer.execute(
                        "UPDATE jobs SET status='failed',summary=NULL WHERE id='changing'"
                    )
                changed = True
            return cursor

    @contextmanager
    def database():
        with original() as db:
            yield ConcurrentWrite(db)

    monkeypatch.setattr(store, "database", database)
    monkeypatch.setattr(store, "diagnostics_snapshot", lambda: {})
    board = store.board(3)
    assert changed
    assert board["counts"]["passed"] == 1
    assert board["stats"]["tests"] == 1
    assert sum(row["passed"] for row in board["timeline"]) == 1
    assert board["coverage"]["result_jobs"] == 1
    assert board["profile_usage"][0]["seconds"] == 1
