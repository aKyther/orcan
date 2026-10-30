"""Sanitized Redis health and local execution-lock diagnostics, never project logs."""

import fcntl
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from . import events, store
from .readiness import lanes
from .settings import state_dir


def lock_held(path: Path) -> bool | None:
    try:
        with path.open("r") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return False
            except BlockingIOError:
                return True
    except FileNotFoundError:
        return False
    except OSError:
        return None  # Unreadable is not proof that execution stopped.


def age_seconds(value: str | None) -> float | None:
    try:
        timestamp = datetime.fromisoformat(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return max(0, round((datetime.now(UTC) - timestamp).total_seconds(), 3))
    except (ValueError, TypeError):
        return None


def jobs() -> dict:
    with store.database() as db:
        oldest = db.execute("SELECT MIN(created) FROM jobs WHERE status='queued'").fetchone()[0]
        rows = list(
            db.execute(
                "SELECT id,sha,status,lane,publication_state,created FROM jobs "
                "WHERE status IN ('queued','running') ORDER BY status DESC,created LIMIT 100"
            )
        )
    result = []
    for row in rows:
        item = dict(row)
        held = lock_held(state_dir() / "jobs" / item["id"] / "run.lock")
        item["execution_lock"] = "held" if held else "free" if held is False else "unknown"
        item["condition"] = (
            "interrupted"
            if item["status"] == "running" and held is False
            else "execution_present"
            if held
            else "unverifiable"
            if held is None
            else "queued"
        )
        result.append(item)
    return {
        "oldest_queued_seconds": age_seconds(oldest),
        "inspected_limit": 100,
        "interrupted": sum(item["condition"] == "interrupted" for item in result),
        "jobs": result,
    }


def sample() -> dict:
    snapshot = {
        "sampled_at": store.now(),
        "status": "disabled",
        "warnings": [],
        "jobs": jobs(),
        "redis": {},
        "lanes": {},
    }
    if snapshot["jobs"]["interrupted"]:
        snapshot["warnings"].append("interrupted_jobs")
    if os.environ.get("ORCAN_REDIS_ENABLED") != "1":
        return snapshot
    connection = None
    began = time.monotonic()
    try:
        connection = events.client()
        snapshot["status"] = "online" if connection.ping() else "offline"
        snapshot["ping_ms"] = round((time.monotonic() - began) * 1000, 3)
        info = connection.info()
        numeric = {
            "used_memory": "used_memory_bytes",
            "maxmemory": "maxmemory_bytes",
            "evicted_keys": "evicted_keys",
            "rejected_connections": "rejected_connections",
            "total_error_replies": "error_replies",
            "uptime_in_seconds": "uptime_seconds",
            "aof_enabled": "aof_enabled",
            "loading": "loading",
        }
        snapshot["redis"] = {
            target: info[key]
            for key, target in numeric.items()
            if type(info.get(key)) in (int, float)
        }
        snapshot["redis"]["aof_write_status"] = (
            info.get("aof_last_write_status")
            if info.get("aof_last_write_status") in {"ok", "err"}
            else "unknown"
        )
        maximum = snapshot["redis"].get("maxmemory_bytes", 0)
        if maximum:
            percent = round(100 * snapshot["redis"].get("used_memory_bytes", 0) / maximum, 2)
            snapshot["redis"]["memory_percent"] = percent
            if percent >= 85:
                snapshot["warnings"].append("redis_memory_pressure")
        if info.get("aof_enabled") == 0:
            snapshot["warnings"].append("aof_disabled")
        if info.get("aof_last_write_status") == "err":
            snapshot["warnings"].append("aof_write_error")
        if snapshot["redis"].get("evicted_keys", 0):
            snapshot["warnings"].append("redis_evictions_recorded")
        snapshot["lanes"] = lanes()
        if any(value["configured"] and not value["ready"] for value in snapshot["lanes"].values()):
            snapshot["warnings"].append("worker_unavailable")
    except Exception:
        # No broker URL, exception text, client list, configuration or credentials.
        snapshot["status"] = "degraded" if snapshot["status"] == "online" else "offline"
        snapshot["warnings"].append("redis_diagnostics_unavailable")
    finally:
        if connection is not None:
            connection.close()
    return snapshot
