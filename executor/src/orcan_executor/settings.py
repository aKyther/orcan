"""Instance-local runtime settings. No dotenv or project secrets are loaded."""

import os
import re
from pathlib import Path

HISTORY_DAYS = 30
HISTORY_LIMIT = 10000


def namespace() -> str:
    value = os.environ.get("ORCAN_NAMED_INSTANCE") or "default"
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", value):
        raise ValueError("Invalid executor instance namespace")
    return value


def state_dir() -> Path:
    default = str(Path.home() / ".local/share/orcan/history/executor" / namespace())
    return Path(os.environ.get("ORCAN_EXECUTOR_STATE_DIR", default)).expanduser().resolve()


def worktree_root() -> Path:
    return (
        Path(os.environ.get("ORCAN_EXECUTOR_WORKTREE_DIR", str(state_dir() / "worktrees")))
        .expanduser()
        .resolve()
    )


def broker_url() -> str:
    return os.environ.get("ORCAN_EXECUTOR_BROKER_URL", "redis://127.0.0.1:6379/0")


def queue_name() -> str:
    return os.environ.get("ORCAN_EXECUTOR_QUEUE", "orcan-executor-" + namespace())


def stream_name() -> str:
    return queue_name() + ":results"


def integer(key: str, default: int, maximum: int) -> int:
    if not 1 <= default <= maximum:
        raise ValueError("Invalid executor limit: " + key)
    return default


def retention_seconds() -> int:
    value = int(os.environ.get("ORCAN_EXECUTOR_RETENTION_SECONDS", "3600"))
    if not 60 <= value <= 86400:
        raise ValueError("Retention must be between 60 and 86400 seconds")
    return value


def max_pending() -> int:
    value = int(os.environ.get("ORCAN_EXECUTOR_MAX_PENDING", "100"))
    if not 1 <= value <= 10000:
        raise ValueError("Pending limit must be between 1 and 10000")
    return value
