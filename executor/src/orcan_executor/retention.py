"""Bounded communication history and completed artifacts; active work is never pruned."""

import fcntl
import json
import shutil
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import store
from .settings import HISTORY_DAYS, HISTORY_LIMIT, retention_seconds, state_dir, worktree_root


def prune() -> int:
    cutoff = (datetime.now(UTC) - timedelta(seconds=retention_seconds())).isoformat()
    removed = 0
    # Only our terminal jobs, under a job lock. A dirty retained worktree is preserved.
    with store.database() as db:
        jobs = list(
            db.execute(
                "SELECT * FROM jobs WHERE details_expired=0 AND finished < ? AND status IN ('passed','failed','error','timed_out','cancelled')",
                (cutoff,),
            )
        )
    for job in jobs:
        directory = state_dir() / "jobs" / job["id"]
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "run.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                continue
            if job["worktree"] and Path(job["worktree"]).exists():
                worktree = Path(job["worktree"]).resolve()
                if not worktree.is_relative_to(worktree_root()):
                    continue
                cleanup = subprocess.run(
                    ["git", "--git-dir", job["git_dir"], "worktree", "remove", str(worktree)],
                    capture_output=True,
                )
                if cleanup.returncode:
                    # Keep user-modified/dirty checkout and metadata for manual inspection.
                    continue
            unpin = subprocess.run(
                [
                    "git",
                    "--git-dir",
                    job["git_dir"],
                    "update-ref",
                    "-d",
                    "refs/orcan/executor/jobs/" + job["id"],
                    job["sha"],
                ],
                capture_output=True,
            )
            if unpin.returncode:
                continue
            with store.database() as db:
                db.execute(
                    "DELETE FROM events WHERE json_extract(payload, '$.job_id') = ?", (job["id"],)
                )
                summary = json.loads(job["summary"] or "{}")
                # Keep counters and measurements, never diagnostic text or artifact paths.
                compact = {
                    key: value
                    for key, value in summary.items()
                    if key in {"tests", "passed", "failed", "errors", "skipped", "seconds"}
                    and isinstance(value, (int, float))
                }
                compact["metrics"] = {
                    key: value
                    for key, value in summary.get("metrics", {}).items()
                    if isinstance(value, (int, float)) or value is None
                }
                db.execute(
                    "UPDATE jobs SET details_expired=1,summary=?,report=NULL,worktree=NULL,"
                    "progress=NULL,selectors='[]',git_dir=NULL WHERE id=?",
                    (json.dumps(compact), job["id"]),
                )
                db.execute(
                    "UPDATE deliveries SET status='expired',reason='Result details expired before delivery' "
                    "WHERE job_id=? AND status='pending'",
                    (job["id"],),
                )
            shutil.rmtree(directory)
            removed += 1
    history_cutoff = (datetime.now(UTC) - timedelta(days=HISTORY_DAYS)).isoformat()
    with store.database() as db:
        # Active jobs and dirty retained worktrees are outside both history limits.
        db.execute(
            "DELETE FROM jobs WHERE details_expired=1 AND (finished < ? OR id IN "
            "(SELECT id FROM jobs WHERE details_expired=1 ORDER BY finished DESC LIMIT -1 OFFSET ?))",
            (history_cutoff, HISTORY_LIMIT),
        )
        db.execute(
            "DELETE FROM fairness WHERE served_at<? AND NOT EXISTS (SELECT 1 FROM jobs "
            "WHERE status IN ('queued','running') AND COALESCE(git_dir,repo)=fairness.repo_key)",
            (history_cutoff,),
        )
        db.execute("DELETE FROM deliveries WHERE job_id NOT IN (SELECT id FROM jobs)")
        db.execute(
            "DELETE FROM events WHERE json_extract(payload,'$.job_id') IS NOT NULL "
            "AND json_extract(payload,'$.job_id') NOT IN (SELECT id FROM jobs)"
        )
    return removed


def maintain():
    from . import events
    from .diagnostics import sample

    while True:
        prune()
        from .snapshots import prune_snapshots

        prune_snapshots()
        store.save_health(sample())
        try:
            events.publish_pending()
            connection = events.client()
            connection.xtrim(
                events.stream_name(),
                minid=str(int((time.time() - retention_seconds()) * 1000)) + "-0",
                approximate=False,
            )
        except Exception:
            pass  # Broker outage cannot discard the durable outbox.
        time.sleep(30)  # Local retention only; no agent/status polling.
