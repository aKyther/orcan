"""Bounded communication history and completed artifacts; active work is never pruned."""

import fcntl
import shutil
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import store
from .settings import retention_seconds, state_dir, worktree_root


def prune() -> int:
    cutoff = (datetime.now(UTC) - timedelta(seconds=retention_seconds())).isoformat()
    removed = 0
    # Only our terminal jobs, under a job lock. A dirty retained worktree is preserved.
    with store.database() as db:
        jobs = list(
            db.execute(
                "SELECT * FROM jobs WHERE finished < ? AND status IN ('passed','failed','error','timed_out','cancelled')",
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
                db.execute("DELETE FROM deliveries WHERE job_id=?", (job["id"],))
                db.execute("DELETE FROM jobs WHERE id=?", (job["id"],))
            shutil.rmtree(directory)
            removed += 1
    return removed


def maintain():
    from . import events

    while True:
        prune()
        from .snapshots import prune_snapshots

        prune_snapshots()
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
