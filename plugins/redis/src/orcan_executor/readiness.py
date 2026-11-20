"""Bounded readiness for each worker: its own live lease and local process lock."""

import fcntl
from datetime import datetime

from . import events
from .settings import queue_name, split_lanes, state_dir, worker_count

LANES = ("default", "light", "heavy")


def worker_lock(lane: str, slot: int = 1) -> str:
    suffix = "" if lane == "default" else "-" + lane
    return "worker" + suffix + ("" if slot == 1 else "-" + str(slot)) + ".lock"


def worker_lease(queue: str, slot: int = 1) -> str:
    return queue + ":worker-ready" + ("" if slot == 1 else ":" + str(slot))


def lanes() -> dict:
    result = {}
    connection = events.client()
    count = worker_count()
    try:
        for lane in LANES:
            configured = lane == "default" or split_lanes()
            queue = queue_name() + ("" if lane == "default" else ":" + lane)
            workers = []
            for slot in range(1, (count if lane == "default" else 1) + 1):
                path = state_dir() / worker_lock(lane, slot)
                locked = False
                if path.exists():
                    with path.open("a") as handle:
                        try:
                            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except BlockingIOError:
                            locked = True
                value = connection.get(worker_lease(queue, slot))
                try:
                    seen = (
                        value
                        if isinstance(value, str) and datetime.fromisoformat(value).tzinfo
                        else None
                    )
                except ValueError:
                    seen = None
                workers.append(
                    dict(
                        slot=slot,
                        ready=locked and bool(value),
                        worker_lock_held=locked,
                        last_heartbeat=seen,
                    )
                )
            result[lane] = {
                "configured": configured,
                "ready": any(worker["ready"] for worker in workers),
                "worker_lock_held": any(worker["worker_lock_held"] for worker in workers),
                "last_heartbeat": max(
                    (worker["last_heartbeat"] for worker in workers if worker["last_heartbeat"]),
                    default=None,
                ),
                "configured_workers": len(workers) if configured else 0,
                "ready_workers": sum(worker["ready"] for worker in workers),
                "workers": workers,
            }
    finally:
        connection.close()
    return result


def admission(services_ready: bool) -> dict:
    """Snapshot of start constraints; each job rechecks admission atomically."""
    from . import store
    from .settings import max_running
    from .storage import capacity

    reasons = []
    if not services_ready:
        reasons.append("services_unavailable")
    try:
        disks = capacity()
        if not disks["ready"]:
            reasons.append("disk_space")
    except (OSError, ValueError):
        disks = {"ready": False, "filesystems": []}
        reasons.append("storage_unavailable")
    with store.database() as db:
        running = db.execute("SELECT COUNT(*) FROM jobs WHERE status='running'").fetchone()[0]
    limit = max_running()
    if running >= limit:
        reasons.append("capacity")
    messages = {
        "services_unavailable": "Executor services are not ready; inspect doctor and diagnostics.",
        "disk_space": "Insufficient free disk space; inspect executor storage and preview storage clean.",
        "storage_unavailable": "Cannot inspect storage; check mounted storage availability and permissions.",
        "capacity": "All execution slots are occupied; queued jobs wait for a free slot.",
    }
    details = [
        f"{disk['path']}: {disk['free_bytes'] // 1024**2} MiB free; "
        f"{disk['minimum_free_bytes'] // 1024**2} MiB required."
        for disk in disks["filesystems"] if not disk["ready"]
    ]
    return {
        "ready": not reasons,
        "reasons": reasons,
        "messages": [messages[reason] for reason in reasons] + details,
        "filesystems": disks["filesystems"],
        "running": running,
        "max_running": limit,
        "note": "Snapshot only; repository scheduling and each job's admission are rechecked at execution.",
    }
