"""Bounded communication history and completed artifacts; active work is never pruned."""

import fcntl
import json
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import store, worktree_cleanup
from .settings import (
    HISTORY_DAYS,
    HISTORY_LIMIT,
    artifact_job_directory,
    retention_seconds,
    state_dir,
    storage_limit_mb,
    worktree_root,
)


def prune(
    *, dry_run: bool = False, candidates: list | None = None, clean_reports: bool = False
) -> int:
    from .storage import capacity, size

    try:
        low_space = not capacity()["ready"]
    except (OSError, ValueError):
        low_space = False  # Unknown/offline storage is not permission to reclaim data.

    if not dry_run:
        expire_interrupted()
    cutoff = (datetime.now(UTC) - timedelta(seconds=retention_seconds())).isoformat()
    removed = 0
    with store.database() as db:
        jobs = list(
            db.execute(
                "SELECT * FROM jobs WHERE status IN ('passed','failed','error','timed_out','cancelled') AND (details_expired=0 OR worktree IS NOT NULL OR git_dir IS NOT NULL) ORDER BY finished,id"
            )
        )
    sizes = {}
    for job in jobs:
        try:
            payload = (
                state_dir() / "jobs" / job["id"]
                if job["details_expired"]
                else artifact_job_directory(dict(job))
            )
            sizes[job["id"]] = size(payload)["allocated_bytes"]
        except (OSError, ValueError):
            continue  # Unavailable external storage must never trigger local fallback/deletion.
    total = sum(sizes.values())
    budget = storage_limit_mb("detail_budget_mb") * 1024**2
    for job in jobs:
        if (
            job["id"] not in sizes
            or not job["finished"]
            or (job["finished"] >= cutoff and total <= budget and not low_space)
        ):
            continue
        expire_details = job["finished"] < cutoff or total > budget
        directory = state_dir() / "jobs" / job["id"]
        if directory.is_symlink():
            continue
        try:
            directory.mkdir(parents=True, exist_ok=True)
            lock = os.fdopen(
                os.open(directory / "run.lock", os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600),
                "a",
            )
        except OSError:
            continue
        with lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                continue
            try:
                fresh = store.get(job["id"])
            except ValueError:
                continue
            if fresh["status"] not in store.TERMINAL:
                continue
            try:
                payload = directory if fresh["details_expired"] else artifact_job_directory(fresh)
            except (OSError, ValueError):
                continue
            if payload.is_symlink():
                continue
            # Modified/locked/foreign trees are retained independently of log TTL.
            retained = fresh.get("worktree")
            git_dir = fresh.get("git_dir")
            clean = False
            if retained and not Path(retained).is_symlink():
                tree = Path(retained)
                if not tree.exists():
                    retained = None
                elif tree.resolve().is_relative_to(worktree_root()):
                    try:
                        definition = fresh.get("profile_definition") or {}
                        if clean_reports or definition.get("cleanup_archived_reports"):
                            if not definition:
                                from . import profiles

                                definition = profiles.for_job(fresh)
                            worktree_cleanup.archived_reports(
                                tree,
                                payload / str(fresh["attempts"]) / "junit",
                                definition,
                                dry_run=dry_run,
                            )
                        clean = worktree_cleanup.removable(tree, definition)
                    except (OSError, ValueError, subprocess.SubprocessError):
                        pass
            changed = (
                not fresh["details_expired"]
                or clean
                or (fresh.get("worktree") and not retained)
                or (not retained and git_dir)
            )
            if not expire_details and not (clean or (not retained and git_dir)):
                continue
            if not changed:
                continue
            if dry_run:
                if candidates is not None and len(candidates) < 50:
                    candidates.append(
                        {
                            "job_id": job["id"],
                            "artifacts": str(payload) if expire_details and not fresh["details_expired"] else None,
                            "worktree": retained if clean else None,
                            "retained_worktree": retained if not clean else None,
                            "reason": ("ttl" if job["finished"] < cutoff else "detail_budget")
                            if expire_details else "disk_space",
                        }
                    )
                total -= sizes[job["id"]]
                removed += 1
                continue
            if clean:
                try:
                    result = subprocess.run(
                        ["git", "--git-dir", git_dir, "worktree", "remove", retained],
                        capture_output=True,
                        timeout=30,
                    )
                    if result.returncode == 0:
                        parent = Path(retained).parent
                        retained = None
                        if (
                            parent.name == job["id"]
                            and parent.parent == worktree_root()
                            and not parent.is_symlink()
                        ):
                            try:
                                parent.rmdir()
                            except OSError:
                                pass
                except (OSError, subprocess.SubprocessError):
                    pass
            if not retained and git_dir:
                try:
                    result = subprocess.run(
                        [
                            "git",
                            "--git-dir",
                            git_dir,
                            "update-ref",
                            "-d",
                            "refs/orcan/executor/jobs/" + job["id"],
                            job["sha"],
                        ],
                        capture_output=True,
                        timeout=10,
                    )
                    if result.returncode == 0:
                        git_dir = None
                except (OSError, subprocess.SubprocessError):
                    pass
            if not expire_details:
                # Reclaim disposable completed trees under pressure, preserving fresh evidence.
                summary = dict(fresh["summary"] or {})
                if not retained:
                    summary.pop("retained_worktree", None)
                with store.database() as db:
                    db.execute(
                        "UPDATE jobs SET worktree=?,git_dir=?,summary=? WHERE id=?",
                        (retained, git_dir, json.dumps(summary), job["id"]),
                    )
                removed += int(not retained)
                # Stop pressure cleanup once the reserve has been restored.
                try:
                    low_space = not capacity()["ready"]
                except (OSError, ValueError):
                    low_space = False
                continue
            # Keep the lock stable while artifact removal and metadata expiry run.
            try:
                for child in payload.iterdir() if payload.exists() else []:
                    if payload == directory and child.name == "run.lock":
                        continue
                    if child.is_dir() and not child.is_symlink():
                        shutil.rmtree(child)
                    else:
                        child.unlink()
                if payload != directory and payload.exists():
                    payload.rmdir()
            except OSError:
                continue  # Retry incomplete artifact removal on the next maintenance pass.
            summary = fresh["summary"] or {}
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
            if summary.get("verification"):
                compact["verification"] = {
                    key: value
                    for key, value in summary["verification"].items()
                    if key != "evidence"
                }
            if retained:
                compact["retained_worktree"] = retained
            with store.database() as db:
                db.execute(
                    "DELETE FROM events WHERE json_extract(payload, '$.job_id') = ?", (job["id"],)
                )
                db.execute(
                    "UPDATE jobs SET details_expired=1,summary=?,report=NULL,worktree=?,progress=NULL,selectors='[]',git_dir=?,evidence_manifest=NULL WHERE id=?",
                    (json.dumps(compact), retained, git_dir, job["id"]),
                )
                db.execute(
                    "UPDATE deliveries SET status='expired',reason='Result details expired before delivery' WHERE job_id=? AND status='pending'",
                    (job["id"],),
                )
            if not retained and not git_dir:
                # This terminal job has no remaining filesystem work to retry.
                # Retained checkouts keep their lock; retired jobs need no directory.
                try:
                    (directory / "run.lock").unlink()
                    directory.rmdir()
                except OSError:
                    pass
            total -= sizes[job["id"]]
            removed += 1
    if dry_run:
        return removed
    history_cutoff = (datetime.now(UTC) - timedelta(days=HISTORY_DAYS)).isoformat()
    with store.database() as db:
        db.execute(
            "DELETE FROM submissions WHERE created<? OR id IN "
            "(SELECT id FROM submissions ORDER BY created DESC,id DESC LIMIT -1 OFFSET ?)",
            (history_cutoff, HISTORY_LIMIT),
        )
        # Active jobs and dirty retained worktrees are outside both history limits.
        expired = db.execute(
            "DELETE FROM jobs WHERE details_expired=1 AND worktree IS NULL AND git_dir IS NULL AND (finished < ? OR id IN "
            "(SELECT id FROM jobs WHERE details_expired=1 AND worktree IS NULL AND git_dir IS NULL ORDER BY finished DESC LIMIT -1 OFFSET ?)) RETURNING id",
            (history_cutoff, HISTORY_LIMIT),
        ).fetchall()
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
    for row in expired:
        directory = state_dir() / "jobs" / row["id"]
        if directory.is_symlink():
            continue
        try:
            # Only an empty expired job marker; never remove unexpected residual files.
            if [path.name for path in directory.iterdir()] == ["run.lock"]:
                with (directory / "run.lock").open("a") as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    (directory / "run.lock").unlink()
                    directory.rmdir()
        except OSError:
            pass
    return removed


def expire_interrupted() -> int:
    """Close overdue abandoned attempts without rerunning them or killing children."""
    cutoff = datetime.now(UTC)
    with store.database() as db:
        jobs = list(db.execute("SELECT id FROM jobs WHERE status='running'"))
    expired = 0
    for row in jobs:
        directory = state_dir() / "jobs" / row["id"]
        if directory.is_symlink():
            continue
        try:
            with os.fdopen(
                os.open(directory / "run.lock", os.O_WRONLY | os.O_NOFOLLOW), "a"
            ) as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                job = store.get(row["id"])
                if job["status"] != "running" or not job["started"]:
                    continue
                deadline = datetime.fromisoformat(job["started"]) + timedelta(
                    seconds=job["timeout"] + 60
                )
                if deadline > cutoff:
                    continue
                store.finish(
                    job["id"],
                    "error",
                    {
                        "error": "Interrupted execution: timeout elapsed and execution lock is free; "
                        "no automatic retry. Inspect retained evidence before resubmitting."
                    },
                    None,
                )
                expired += 1
        except (OSError, ValueError):
            continue  # Missing/unreadable metadata is not proof that execution stopped.
    return expired


def maintain():
    from . import events
    from .diagnostics import sample
    from .engine import expire_queued_jobs

    while True:
        expire_queued_jobs()
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
