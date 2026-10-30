"""Bounded lane readiness: a live lease plus the matching local worker lock."""

import fcntl
import os
from datetime import datetime

from . import events
from .settings import queue_name, state_dir

LANES = ("default", "light", "heavy")


def lanes() -> dict:
    result = {}
    connection = events.client()
    try:
        for lane in LANES:
            configured = lane == "default" or os.environ.get("ORCAN_EXECUTOR_SPLIT_LANES") == "1"
            suffix = "" if lane == "default" else ":" + lane
            lock_name = "worker.lock" if lane == "default" else "worker-" + lane + ".lock"
            path = state_dir() / lock_name
            locked = False
            if path.exists():
                with path.open("a") as handle:
                    try:
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        locked = True
            value = connection.get(queue_name() + suffix + ":worker-ready")
            try:
                seen = (
                    value
                    if isinstance(value, str) and datetime.fromisoformat(value).tzinfo
                    else None
                )
            except ValueError:
                seen = None
            result[lane] = {
                "configured": configured,
                "ready": locked and bool(value),
                "worker_lock_held": locked,
                "last_heartbeat": seen,
            }
    finally:
        connection.close()
    return result
