import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .metrics import measure_result, wire
from .settings import retention_seconds, state_dir

TERMINAL = {"passed", "failed", "error", "timed_out"}


def now() -> str:
    return datetime.now(UTC).isoformat()


@contextmanager
def database(directory: Path | None = None):
    root = directory or state_dir()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    connection = sqlite3.connect(root / "jobs.sqlite", timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, repo TEXT NOT NULL, git_dir TEXT, sha TEXT NOT NULL,
                task TEXT NOT NULL, profile TEXT NOT NULL, selectors TEXT NOT NULL,
                timeout INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
                attempts INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL,
                started TEXT, finished TEXT, summary TEXT, report TEXT, worktree TEXT
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL,
                published INTEGER NOT NULL DEFAULT 0
            );
        """)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
        if "git_dir" not in columns:
            connection.execute("ALTER TABLE jobs ADD COLUMN git_dir TEXT")
        if "progress" not in columns:
            connection.execute("ALTER TABLE jobs ADD COLUMN progress TEXT")
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def event(db, payload: dict) -> dict:
    cursor = db.execute("INSERT INTO events(payload) VALUES(?)", ("{}",))
    payload["event_id"] = cursor.lastrowid
    measure_result(payload)
    db.execute("UPDATE events SET payload=? WHERE id=?", (wire(payload), cursor.lastrowid))
    return payload


def create(job: dict) -> None:
    with database() as db:
        db.execute(
            "INSERT INTO jobs(id,repo,git_dir,sha,task,profile,selectors,timeout,created) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                job["id"],
                job["repo"],
                job["git_dir"],
                job["sha"],
                job["task"],
                job["profile"],
                json.dumps(job["selectors"]),
                job["timeout"],
                now(),
            ),
        )
        event(
            db,
            {
                "kind": "queued",
                "job_id": job["id"],
                "task_id": job["task"],
                "sha": job["sha"],
                "status": "queued",
            },
        )


def get(job_id: str) -> dict:
    with database() as db:
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        raise ValueError("Unknown job ID: " + job_id)
    result = dict(row)
    result["selectors"] = json.loads(result["selectors"])
    if result["summary"] is not None:
        result["summary"] = json.loads(result["summary"])
    return result


def listing(failures: bool = False) -> list[dict]:
    with database() as db:
        where = "WHERE status IN ('failed','error','timed_out')" if failures else ""
        return [
            dict(row)
            for row in db.execute(
                "SELECT id,task,sha,profile,status,attempts,created,report,worktree FROM jobs "
                + where
                + " ORDER BY created DESC LIMIT 100"
            )
        ]


def start(job_id: str, worktree: Path) -> None:
    with database() as db:
        db.execute(
            "UPDATE jobs SET status='running', attempts=attempts+1, started=?, finished=NULL, worktree=? WHERE id=?",
            (now(), str(worktree), job_id),
        )
        row = db.execute("SELECT task,sha FROM jobs WHERE id=?", (job_id,)).fetchone()
        event(
            db,
            {
                "kind": "running",
                "job_id": job_id,
                "task_id": row["task"],
                "sha": row["sha"],
                "status": "running",
                "worktree": str(worktree),
            },
        )


def finish(job_id: str, status: str, summary: dict, report: Path) -> dict:
    if status not in TERMINAL:
        raise ValueError("Expected a terminal status")
    with database() as db:
        row = db.execute("SELECT task,sha,attempts FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown job ID")
        payload = {
            "job_id": job_id,
            "task_id": row["task"],
            "sha": row["sha"],
            "attempt": row["attempts"],
            "status": status,
            "summary": summary,
            "report": str(report),
        }
        payload["kind"] = "finished"
        event(db, payload)
        db.execute(
            "UPDATE jobs SET status=?,finished=?,summary=?,report=? WHERE id=?",
            (status, now(), json.dumps(summary), str(report), job_id),
        )
    return payload


def unpublished(replay: bool = False) -> list[dict]:
    with database() as db:
        return [
            dict(row)
            for row in db.execute(
                "SELECT id,payload FROM events "
                + ("" if replay else "WHERE published=0 ")
                + "ORDER BY id"
            )
        ]


def mark_published(event_id: int) -> None:
    with database() as db:
        db.execute("UPDATE events SET published=1 WHERE id=?", (event_id,))


def board() -> dict:
    with database() as db:
        counts = {
            state: 0 for state in ("queued", "running", "passed", "failed", "error", "timed_out")
        }
        counts.update(
            {
                row["status"]: row["amount"]
                for row in db.execute("SELECT status,COUNT(*) AS amount FROM jobs GROUP BY status")
            }
        )
        jobs = [
            dict(row) for row in db.execute("SELECT * FROM jobs ORDER BY created DESC LIMIT 100")
        ]
        aggregate = dict(
            db.execute("""
            SELECT COUNT(summary) AS completed_jobs,
            COALESCE(SUM(json_extract(summary, '$.metrics.log_bytes')),0) AS log_bytes,
            COALESCE(SUM(json_extract(summary, '$.metrics.log_lines')),0) AS log_lines,
            COALESCE(SUM(json_extract(summary, '$.metrics.result_bytes')),0) AS result_bytes,
            COALESCE(SUM(json_extract(summary, '$.tests')),0) AS tests,
            COALESCE(SUM(json_extract(summary, '$.skipped')),0) AS skipped,
            COALESCE(AVG(json_extract(summary, '$.metrics.queue_seconds')),0) AS average_queue_seconds,
            COALESCE(AVG(json_extract(summary, '$.seconds')),0) AS average_run_seconds,
            COALESCE(SUM(json_extract(summary, '$.metrics.executor_cpu_seconds')),0) AS executor_cpu_seconds
            FROM jobs WHERE summary IS NOT NULL
        """).fetchone()
        )
    for job in jobs:
        job["selectors"] = json.loads(job["selectors"])
        job["summary"] = json.loads(job["summary"]) if job["summary"] else None
    for job in jobs:
        job["progress"] = json.loads(job["progress"]) if job.get("progress") else None
    aggregate["reduction_bytes"] = aggregate["log_bytes"] - aggregate["result_bytes"]
    aggregate["reduction_percent"] = (
        round(100 * aggregate["reduction_bytes"] / aggregate["log_bytes"], 2)
        if aggregate["log_bytes"]
        else None
    )
    aggregate["estimated_tokens_avoided"] = max(0, aggregate["reduction_bytes"] // 4)
    worker_running = False
    lock_path = state_dir() / "worker.lock"
    if lock_path.exists():
        import fcntl

        with lock_path.open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                worker_running = True
    return {
        "counts": counts,
        "jobs": jobs,
        "worker_running": worker_running,
        "stats": aggregate,
        "retention_seconds": retention_seconds(),
    }


def step(job: dict, index: int, status: str, seconds: float | None = None, total: int = 1) -> None:
    with database() as db:
        db.execute(
            "UPDATE jobs SET progress=? WHERE id=?",
            (
                wire({"index": index, "total": total, "status": status, "seconds": seconds}),
                job["id"],
            ),
        )
        event(
            db,
            {
                "total": total,
                "kind": "step",
                "job_id": job["id"],
                "sha": job["sha"],
                "step": index,
                "status": status,
                "seconds": seconds,
            },
        )
