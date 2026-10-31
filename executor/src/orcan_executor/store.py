import json
import math
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .metrics import measure_result, wire
from .settings import (
    HISTORY_DAYS,
    HISTORY_LIMIT,
    effective,
    max_pending,
    max_running,
    retention_seconds,
    state_dir,
)

TERMINAL = {"passed", "failed", "error", "timed_out", "cancelled"}


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
            BEGIN IMMEDIATE;
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, repo TEXT NOT NULL, git_dir TEXT, sha TEXT NOT NULL,
                task TEXT NOT NULL, profile TEXT NOT NULL, selectors TEXT NOT NULL,
                timeout INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
                attempts INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL,
                started TEXT, finished TEXT, summary TEXT, report TEXT, worktree TEXT, progress TEXT
            );
            CREATE TABLE IF NOT EXISTS deliveries (
                job_id TEXT NOT NULL, thread_id TEXT NOT NULL,
                status TEXT NOT NULL, created TEXT NOT NULL, finished TEXT, reason TEXT,
                PRIMARY KEY(job_id,thread_id)
            );
            CREATE TABLE IF NOT EXISTS fairness (
                repo_key TEXT NOT NULL, lane TEXT NOT NULL, last_served INTEGER NOT NULL,
                served_at TEXT NOT NULL, PRIMARY KEY(repo_key,lane)
            );
            CREATE TABLE IF NOT EXISTS communication (
                name TEXT PRIMARY KEY, amount INTEGER NOT NULL DEFAULT 0, updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS health (
                id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL
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
        for name, definition in {
            "details_expired": "INTEGER NOT NULL DEFAULT 0",
            "history_source": "TEXT NOT NULL DEFAULT 'recorded'",
            "lane": "TEXT",
            "publication_state": "TEXT NOT NULL DEFAULT 'unknown'",
            "recovery_count": "INTEGER NOT NULL DEFAULT 0",
            "replace_group": "TEXT",
            "replace_owner": "TEXT",
            "superseded_by": "TEXT",
            "admission_reason": "TEXT",
            "fair_wait_for": "TEXT",
            "fair_wait_started": "TEXT",
            "fairness_bypasses": "INTEGER NOT NULL DEFAULT 0",
            "acknowledged": "TEXT",
            "detail_reads": "INTEGER NOT NULL DEFAULT 0",
            "detail_bytes": "INTEGER NOT NULL DEFAULT 0",
            "detail_wire_bytes": "INTEGER NOT NULL DEFAULT 0",
        }.items():
            if name not in columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN " + name + " " + definition)
        # Recognize records restored by the earlier one-off recovery tool.
        connection.execute(
            "UPDATE jobs SET history_source='recovered' WHERE history_source='recorded' "
            "AND repo='unknown (restored from Redis AOF)'"
        )
        delivery_columns = {row[1] for row in connection.execute("PRAGMA table_info(deliveries)")}
        for name, definition in {
            "message_bytes": "INTEGER NOT NULL DEFAULT 0",
            "adapter_seconds": "REAL NOT NULL DEFAULT 0",
        }.items():
            if name not in delivery_columns:
                connection.execute("ALTER TABLE deliveries ADD COLUMN " + name + " " + definition)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS jobs_replace_scope ON jobs(git_dir,replace_group,replace_owner,status)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS jobs_lane_queue ON jobs(lane,status,publication_state,created)"
        )
        connection.commit()
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


def create(job: dict, reuse: bool = False, replacements: list[str] | None = None) -> str:
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        if reuse:
            existing = db.execute(
                "SELECT id FROM jobs WHERE git_dir=? AND sha=? AND profile=? AND selectors=? AND timeout=? AND status IN ('queued','running') ORDER BY created LIMIT 1",
                (
                    job["git_dir"],
                    job["sha"],
                    job["profile"],
                    json.dumps(job["selectors"]),
                    job["timeout"],
                ),
            ).fetchone()
            if existing:
                return existing["id"]
        replace_ids = {row["id"] for row in _replacement_rows(db, job)} & set(replacements or [])
        count = db.execute(
            "SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')"
        ).fetchone()[0]
        if count - len(replace_ids) >= max_pending():
            raise ValueError(
                "Executor capacity reached; cancel obsolete queued work or wait for a completion event"
            )
        for old_id in sorted(replace_ids):
            db.execute("UPDATE jobs SET superseded_by=? WHERE id=?", (job["id"], old_id))
            _finish(
                db,
                old_id,
                "cancelled",
                {
                    "tests": 0,
                    "passed": 0,
                    "failed": 0,
                    "errors": 0,
                    "skipped": 0,
                    "message": "Superseded before execution by a newer snapshot",
                    "superseded_by": job["id"],
                },
                None,
            )
        db.execute(
            "INSERT INTO jobs(id,repo,git_dir,sha,task,profile,selectors,timeout,created,lane,replace_group,replace_owner) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
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
                job.get("lane", "default"),
                job.get("replace_group"),
                job.get("replace_owner"),
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

    return job["id"]


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


def start(job_id: str, worktree: Path) -> bool:
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        running = db.execute(
            "SELECT COUNT(*) FROM jobs WHERE status='running' AND id<>?", (job_id,)
        ).fetchone()[0]
        if running >= max_running():
            db.execute(
                "UPDATE jobs SET admission_reason='capacity' WHERE id=? AND status='queued' "
                "AND COALESCE(admission_reason,'')<>'capacity'",
                (job_id,),
            )
            return False
        candidate = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if candidate is None or candidate["status"] not in {"queued", "running"}:
            return False
        lane = candidate["lane"] or "default"
        winner = db.execute(
            "SELECT j.id FROM jobs j LEFT JOIN fairness f "
            "ON f.repo_key=COALESCE(j.git_dir,j.repo) AND f.lane=COALESCE(j.lane,'default') "
            "WHERE COALESCE(j.lane,'default')=? AND (j.status='queued' OR (j.id=? AND j.status='running')) "
            "AND (j.publication_state='published' OR j.id=?) "
            "ORDER BY COALESCE(f.last_served,0),j.created,j.id LIMIT 1",
            (lane, job_id, job_id),
        ).fetchone()
        bypass = False
        if candidate["status"] == "queued" and winner is not None and winner["id"] != job_id:
            since = candidate["fair_wait_started"]
            if candidate["fair_wait_for"] != winner["id"] or not since:
                db.execute(
                    "UPDATE jobs SET admission_reason='fair_turn',fair_wait_for=?,fair_wait_started=? WHERE id=?",
                    (winner["id"], now(), job_id),
                )
                return False
            waited = (datetime.now(UTC) - datetime.fromisoformat(since)).total_seconds()
            if waited < 30:
                return False
            # A published row may outlive a lost broker message. Do not let one
            # absent delivery block every other repo forever; never run it here.
            bypass = True
        db.execute(
            "UPDATE jobs SET status='running', admission_reason=NULL, fair_wait_for=NULL,fair_wait_started=NULL,"
            "fairness_bypasses=fairness_bypasses+?, attempts=attempts+1, started=?, finished=NULL, worktree=? WHERE id=?",
            (int(bypass), now(), str(worktree), job_id),
        )
        row = db.execute("SELECT task,sha FROM jobs WHERE id=?", (job_id,)).fetchone()
        turn = event(
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

        db.execute(
            "INSERT INTO fairness(repo_key,lane,last_served,served_at) VALUES(?,?,?,?) "
            "ON CONFLICT(repo_key,lane) DO UPDATE SET last_served=excluded.last_served,served_at=excluded.served_at",
            (candidate["git_dir"] or candidate["repo"], lane, turn["event_id"], now()),
        )
    return True


def finish(job_id: str, status: str, summary: dict, report: Path) -> dict:
    with database() as db:
        return _finish(db, job_id, status, summary, report)


def _finish(db, job_id: str, status: str, summary: dict, report: Path | None) -> dict:
    if status not in TERMINAL:
        raise ValueError("Expected a terminal status")
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
        "report": str(report) if report is not None else None,
    }
    payload["kind"] = "finished"
    event(db, payload)
    db.execute(
        "UPDATE jobs SET status=?,finished=?,summary=?,report=?,admission_reason=NULL WHERE id=?",
        (status, now(), json.dumps(summary), str(report) if report is not None else None, job_id),
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


def board(hours: int | None = None) -> dict:
    if hours is not None and not 1 <= hours <= 720:
        raise ValueError("History window must be between 1 and 720 hours")
    snapshot_time = datetime.now(UTC)
    with database() as db:
        db.execute("BEGIN")
        cutoff = (snapshot_time - timedelta(hours=hours or 720)).isoformat()
        db.execute("CREATE TEMP TABLE history_window(cutoff TEXT)")
        db.execute("INSERT INTO history_window VALUES(?)", (cutoff,))
        db.execute(
            "CREATE TEMP VIEW scoped_jobs AS SELECT * FROM jobs WHERE "
            "status IN ('queued','running') OR COALESCE(finished,created) >= "
            "(SELECT cutoff FROM history_window)"
        )
        db.execute(
            "CREATE TEMP VIEW scoped_deliveries AS SELECT d.* FROM deliveries d "
            "JOIN scoped_jobs j ON j.id=d.job_id"
        )
        counts = {
            state: 0
            for state in (
                "queued",
                "running",
                "passed",
                "failed",
                "error",
                "timed_out",
                "cancelled",
            )
        }
        counts.update(
            {
                row["status"]: row["amount"]
                for row in db.execute(
                    "SELECT status,COUNT(*) AS amount FROM scoped_jobs GROUP BY status"
                )
            }
        )
        jobs = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM scoped_jobs ORDER BY status IN ('queued','running') DESC,created DESC LIMIT 100"
            )
        ]
        aggregate = dict(
            db.execute("""
            SELECT COUNT(*) AS completed_jobs,
            COUNT(json_extract(summary, '$.metrics.result_bytes')) AS measured_result_jobs,
            COALESCE(SUM(superseded_by IS NOT NULL),0) AS superseded_jobs,
            COALESCE(SUM(fairness_bypasses),0) AS fairness_bypasses,
            COALESCE(SUM(json_extract(summary, '$.metrics.log_bytes')),0) AS log_bytes,
            COALESCE(SUM(json_extract(summary, '$.metrics.log_lines')),0) AS log_lines,
            COALESCE(SUM(json_extract(summary, '$.metrics.result_bytes')),0) AS result_bytes,
            COALESCE(SUM(json_extract(summary, '$.tests')),0) AS tests,
            COALESCE(SUM(json_extract(summary, '$.skipped')),0) AS skipped,
            COALESCE(AVG(json_extract(summary, '$.metrics.queue_seconds')),0) AS average_queue_seconds,
            COALESCE(AVG(json_extract(summary, '$.seconds')),0) AS average_run_seconds,
            COALESCE(SUM(json_extract(summary, '$.seconds')),0) AS total_run_seconds,
            COALESCE(SUM(json_extract(summary, '$.metrics.child_cpu_seconds')),0) AS child_cpu_seconds,
            COALESCE(SUM(json_extract(summary, '$.metrics.executor_cpu_seconds')),0) AS executor_cpu_seconds
            FROM scoped_jobs WHERE finished IS NOT NULL
        """).fetchone()
        )
        by_status = [
            dict(row)
            for row in db.execute(
                "SELECT status, COUNT(*) AS jobs, COALESCE(SUM(json_extract(summary, '$.metrics.log_bytes')),0) AS log_bytes, COALESCE(SUM(json_extract(summary, '$.metrics.result_bytes')),0) AS result_bytes FROM scoped_jobs WHERE finished IS NOT NULL GROUP BY status"
            )
        ]
        usage = dict(
            db.execute(
                "SELECT COUNT(acknowledged) AS acknowledged_jobs, COALESCE(SUM(detail_reads),0) AS detail_reads, COALESCE(SUM(detail_bytes),0) AS detail_bytes, COALESCE(SUM(detail_wire_bytes),0) AS detail_wire_bytes FROM scoped_jobs"
            ).fetchone()
        )
        delivery_counts = {
            row["status"]: row["amount"]
            for row in db.execute(
                "SELECT status,COUNT(*) AS amount FROM scoped_deliveries GROUP BY status"
            )
        }
        delivery_jobs = [
            dict(row)
            for row in db.execute(
                "SELECT d.job_id,d.thread_id,d.status,d.reason,d.message_bytes,d.adapter_seconds FROM scoped_deliveries d JOIN (SELECT id FROM scoped_jobs ORDER BY status IN ('queued','running') DESC,created DESC LIMIT 100) j ON d.job_id=j.id ORDER BY d.thread_id"
            )
        ]
        coverage = dict(
            db.execute("""
            SELECT COUNT(*) AS completed_jobs,
            COALESCE(SUM(history_source='recovered'),0) AS recovered_jobs,
            COUNT(json_extract(summary,'$.metrics.log_bytes')) AS log_jobs,
            COUNT(json_extract(summary,'$.metrics.result_bytes')) AS result_jobs,
            COUNT(json_extract(summary,'$.metrics.queue_seconds')) AS queue_jobs,
            COUNT(json_extract(summary,'$.seconds')) AS run_jobs,
            COALESCE(SUM(json_type(summary,'$.metrics.log_bytes') IN ('integer','real') AND
                json_type(summary,'$.metrics.result_bytes') IN ('integer','real')),0) AS compared_jobs,
            COALESCE(SUM(CASE WHEN json_type(summary,'$.metrics.log_bytes') IN ('integer','real') AND
                json_type(summary,'$.metrics.result_bytes') IN ('integer','real')
                THEN json_extract(summary,'$.metrics.log_bytes') END),0) AS compared_log_bytes,
            COALESCE(SUM(CASE WHEN json_type(summary,'$.metrics.log_bytes') IN ('integer','real') AND
                json_type(summary,'$.metrics.result_bytes') IN ('integer','real')
                THEN json_extract(summary,'$.metrics.result_bytes') END),0) AS compared_result_bytes,
            COALESCE(SUM(CASE WHEN history_source<>'recovered' AND
                json_type(summary,'$.metrics.log_bytes') IN ('integer','real') AND
                json_type(summary,'$.metrics.result_bytes') IN ('integer','real')
                THEN json_extract(summary,'$.metrics.log_bytes')-
                json_extract(summary,'$.metrics.result_bytes')-detail_wire_bytes END),0) AS known_reduction_bytes,
            COALESCE(SUM(history_source<>'recovered' AND
                json_type(summary,'$.metrics.result_bytes') IN ('integer','real')),0) AS return_jobs,
            COALESCE(SUM(CASE WHEN history_source<>'recovered' AND
                json_type(summary,'$.metrics.result_bytes') IN ('integer','real')
                THEN json_extract(summary,'$.metrics.result_bytes')+detail_wire_bytes END),0) AS known_return_bytes
            FROM scoped_jobs WHERE finished IS NOT NULL
        """).fetchone()
        )
        notification_stats = dict(
            db.execute("""
            SELECT COALESCE(SUM(message_bytes>0),0) AS attempted_messages,
            COALESCE(SUM(message_bytes),0) AS attempted_bytes,
            COALESCE(SUM(CASE WHEN status IN ('queued','consumed') THEN message_bytes ELSE 0 END),0) AS accepted_bytes,
            COALESCE(SUM(CASE WHEN status='consumed' THEN message_bytes ELSE 0 END),0) AS consumed_bytes,
            COALESCE(SUM(CASE WHEN status='unknown' THEN message_bytes ELSE 0 END),0) AS uncertain_bytes,
            COALESCE(SUM(adapter_seconds),0) AS adapter_seconds FROM scoped_deliveries
        """).fetchone()
        )
        aggregate["by_status"] = by_status
        aggregate.update(usage)
        for job in jobs:
            job["deliveries"] = [d for d in delivery_jobs if d["job_id"] == job["id"]]
            job["selectors"] = json.loads(job["selectors"])
            job["summary"] = json.loads(job["summary"]) if job["summary"] else None
        for job in jobs:
            job["progress"] = json.loads(job["progress"]) if job.get("progress") else None
        aggregate["reduction_bytes"] = (
            coverage["compared_log_bytes"] - coverage["compared_result_bytes"]
        )
        aggregate["reduction_percent"] = (
            round(100 * aggregate["reduction_bytes"] / coverage["compared_log_bytes"], 2)
            if coverage["compared_log_bytes"]
            else None
        )
        aggregate["estimated_tokens_avoided"] = max(0, aggregate["reduction_bytes"] // 4)
        interval = (
            300
            if hours and hours <= 3
            else 3600
            if hours and hours <= 24
            else 21600
            if hours and hours <= 168
            else 86400
        )
        cutoff = (snapshot_time - timedelta(hours=hours or 720)).isoformat()
        timeline = [
            dict(row)
            for row in db.execute(
                "SELECT CAST(strftime('%s',finished) AS INTEGER)/?*? AS bucket, "
                "COUNT(*) AS jobs, SUM(status='passed') AS passed, SUM(status IN ('failed','error','timed_out')) AS problems, SUM(status='cancelled') AS cancelled, "
                "COALESCE(SUM(json_extract(summary,'$.metrics.log_bytes')),0) AS log_bytes, "
                "COALESCE(SUM(json_extract(summary,'$.metrics.result_bytes')),0) AS result_bytes, "
                "COALESCE(SUM(detail_wire_bytes),0) AS detail_wire_bytes, "
                "AVG(json_extract(summary,'$.metrics.queue_seconds')) AS queue_seconds, "
                "AVG(json_extract(summary,'$.seconds')) AS run_seconds "
                "FROM scoped_jobs WHERE finished>=? GROUP BY bucket ORDER BY bucket",
                (interval, interval, cutoff),
            )
        ]
        profiles = [
            dict(row)
            for row in db.execute(
                "SELECT repo,profile,lane,COUNT(*) AS jobs,COALESCE(SUM(json_extract(summary,'$.seconds')),0) AS seconds "
                "FROM scoped_jobs WHERE finished>=? GROUP BY repo,profile,lane ORDER BY jobs DESC LIMIT 20",
                (cutoff,),
            )
        ]
        samples = sorted(
            row[0]
            for row in db.execute(
                "SELECT json_extract(summary,'$.metrics.queue_seconds') FROM scoped_jobs WHERE finished>=? "
                "AND json_type(summary,'$.metrics.queue_seconds') IN ('integer','real')",
                (cutoff,),
            )
        )
        measured_rows = [
            dict(row)
            for row in db.execute(
                "SELECT CAST(strftime('%s',finished) AS INTEGER)/?*? AS bucket, "
                "history_source,summary,detail_wire_bytes FROM scoped_jobs WHERE finished>=?",
                (interval, interval, cutoff),
            )
        ]
        by_bucket = {}
        for row in measured_rows:
            by_bucket.setdefault(row["bucket"], []).append(row)
        for bucket in timeline:
            rows = by_bucket[bucket["bucket"]]
            summaries = [json.loads(row["summary"] or "{}") for row in rows]
            metrics = [summary.get("metrics", {}) for summary in summaries]
            bucket["log_jobs"] = sum(isinstance(m.get("log_bytes"), (int, float)) for m in metrics)
            bucket["result_jobs"] = sum(
                isinstance(m.get("result_bytes"), (int, float)) for m in metrics
            )
            queue = sorted(
                m["queue_seconds"]
                for m in metrics
                if isinstance(m.get("queue_seconds"), (int, float))
            )
            bucket["queue_jobs"] = len(queue)
            bucket["run_jobs"] = sum(isinstance(s.get("seconds"), (int, float)) for s in summaries)
            bucket["queue_p95_seconds"] = queue[math.ceil(len(queue) * 0.95) - 1] if queue else None
            returns = [
                m["result_bytes"] + row["detail_wire_bytes"]
                for row, m in zip(rows, metrics, strict=True)
                if row["history_source"] != "recovered"
                and isinstance(m.get("result_bytes"), (int, float))
            ]
            bucket["return_jobs"] = len(returns)
            bucket["returned_bytes"] = sum(returns) if returns else None
            if not bucket["log_jobs"]:
                bucket["log_bytes"] = None
            if not bucket["result_jobs"]:
                bucket["result_bytes"] = None
    # Include idle buckets, so a line never bridges an unobserved period.
    buckets = {row["bucket"]: row for row in timeline}
    first = int(datetime.fromisoformat(cutoff).timestamp()) // interval * interval
    last = int(snapshot_time.timestamp()) // interval * interval
    timeline = [
        buckets.get(
            stamp,
            dict(
                bucket=stamp,
                jobs=0,
                passed=0,
                problems=0,
                cancelled=0,
                log_bytes=0,
                result_bytes=0,
                detail_wire_bytes=0,
                returned_bytes=0,
                queue_seconds=None,
                run_seconds=None,
                queue_p95_seconds=None,
                log_jobs=0,
                result_jobs=0,
                return_jobs=0,
                queue_jobs=0,
                run_jobs=0,
            ),
        )
        for stamp in range(first, last + 1, interval)
    ]
    aggregate["queue_p50_seconds"] = samples[math.ceil(len(samples) * 0.5) - 1] if samples else None
    aggregate["queue_p95_seconds"] = (
        samples[math.ceil(len(samples) * 0.95) - 1] if samples else None
    )
    aggregate["return_with_details_bytes"] = coverage["known_return_bytes"]
    aggregate["reduction_with_details_bytes"] = coverage["known_reduction_bytes"]
    worker_running = False
    for lock_path in [
        state_dir() / "worker.lock",
        state_dir() / "worker-2.lock",
        state_dir() / "worker-3.lock",
        state_dir() / "worker-4.lock",
        state_dir() / "worker-5.lock",
        state_dir() / "worker-light.lock",
        state_dir() / "worker-heavy.lock",
    ]:
        if lock_path.exists():
            import fcntl

            with lock_path.open("a") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    worker_running = True
    return {
        "counts": counts,
        "coverage": coverage,
        "snapshot_at": snapshot_time.isoformat(),
        "jobs": jobs,
        "timeline": timeline,
        "communication": diagnostics_snapshot(),
        "timeline_bucket_seconds": interval,
        "profile_usage": profiles,
        "settings": effective(),
        "worker_running": worker_running,
        "stats": aggregate,
        "retention_seconds": retention_seconds(),
        "history_days": HISTORY_DAYS,
        "history_limit": HISTORY_LIMIT,
        "window_hours": hours or 720,
        "max_pending": max_pending(),
        "delivery_counts": delivery_counts,
        "notification_stats": notification_stats,
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


def acknowledge(job_id: str) -> None:
    with database() as db:
        row = db.execute("SELECT sha,status FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None or row["status"] not in TERMINAL:
            raise ValueError("Only a completed result can be acknowledged")
        changed = db.execute(
            "UPDATE jobs SET acknowledged=? WHERE id=? AND acknowledged IS NULL", (now(), job_id)
        ).rowcount
        if changed:
            event(
                db,
                {
                    "kind": "acknowledged",
                    "job_id": job_id,
                    "sha": row["sha"],
                    "status": "acknowledged",
                },
            )


def detail_read(job_id: str, size: int, wire_bytes: int = 0) -> None:
    with database() as db:
        db.execute(
            "UPDATE jobs SET detail_reads=detail_reads+1, detail_bytes=detail_bytes+?, detail_wire_bytes=detail_wire_bytes+? WHERE id=?",
            (size, wire_bytes, job_id),
        )
        event(db, {"kind": "detail_read", "job_id": job_id, "bytes": size})


def communication(name: str, amount: int = 1) -> None:
    if name not in {"stream_published", "stream_failures", "enqueue_published", "enqueue_failures"}:
        raise ValueError("Unknown communication counter")
    with database() as db:
        db.execute(
            "INSERT INTO communication(name,amount,updated) VALUES(?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET amount=amount+excluded.amount,updated=excluded.updated",
            (name, amount, now()),
        )


def publication(job_id: str, state: str) -> None:
    if state not in {
        "published",
        "lane_unavailable",
        "readiness_unavailable",
        "uncertain",
        "recovery_pending",
    }:
        raise ValueError("Unknown publication state")
    with database() as db:
        db.execute("UPDATE jobs SET publication_state=? WHERE id=?", (state, job_id))


def save_health(payload: dict) -> None:
    with database() as db:
        db.execute("INSERT OR REPLACE INTO health(id,payload) VALUES(1,?)", (wire(payload),))
        # Coalesce local health events so outages do not build an unbounded outbox.
        db.execute("DELETE FROM events WHERE json_extract(payload,'$.kind')='health'")
        event(db, {"kind": "health", "sampled_at": payload["sampled_at"]})


def diagnostics_snapshot() -> dict:
    with database() as db:
        counters = {
            row["name"]: {"count": row["amount"], "updated": row["updated"]}
            for row in db.execute("SELECT * FROM communication")
        }
        pending = db.execute("SELECT COUNT(*) FROM events WHERE published=0").fetchone()[0]
        row = db.execute("SELECT payload FROM health WHERE id=1").fetchone()
    health = json.loads(row["payload"]) if row else None
    age = None
    if health:
        try:
            age = max(
                0,
                (datetime.now(UTC) - datetime.fromisoformat(health["sampled_at"])).total_seconds(),
            )
        except (ValueError, TypeError, KeyError):
            pass
    return {
        "counters": counters,
        "pending_events": pending,
        "health": health,
        "health_age_seconds": round(age, 1) if age is not None else None,
        "health_stale": age is None or age > 90,
    }


def _replacement_rows(db, job: dict) -> list:
    if not job.get("replace_group"):
        return []
    return list(
        db.execute(
            "SELECT id,sha FROM jobs j WHERE j.status='queued' AND j.sha<>? AND j.git_dir=? "
            "AND j.profile=? AND j.selectors=? AND j.timeout=? AND COALESCE(j.lane,'default')=? "
            "AND j.replace_group=? AND j.replace_owner=? "
            "AND NOT EXISTS (SELECT 1 FROM deliveries d WHERE d.job_id=j.id AND d.thread_id<>?) "
            "ORDER BY j.created,j.id LIMIT 100",
            (
                job["sha"],
                job["git_dir"],
                job["profile"],
                json.dumps(job["selectors"]),
                job["timeout"],
                job.get("lane", "default"),
                job["replace_group"],
                job["replace_owner"],
                job["replace_owner"],
            ),
        )
    )


def replacement_candidates(job: dict) -> list[dict]:
    with database() as db:
        return [dict(row) for row in _replacement_rows(db, job)]


def superseded_count(job_id: str) -> int:
    with database() as db:
        return db.execute("SELECT COUNT(*) FROM jobs WHERE superseded_by=?", (job_id,)).fetchone()[
            0
        ]
