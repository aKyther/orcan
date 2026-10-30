"""Bounded lane readiness: a live lease plus the matching local worker lock."""

import fcntl
import os

from . import events
from .settings import queue_name, state_dir

LANES = ("default", "light", "heavy")


def lanes() -> dict:
    result = {}
    connection = events.client()
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
        lease = bool(connection.get(queue_name() + suffix + ":worker-ready"))
        result[lane] = {"configured": configured, "ready": locked and lease}
    return result
