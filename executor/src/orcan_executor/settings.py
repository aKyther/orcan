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


def max_running() -> int:
    value = int(os.environ.get("ORCAN_EXECUTOR_MAX_RUNNING", "2"))
    if not 1 <= value <= 3:
        raise ValueError("Running limit must be between 1 and 3")
    return value


def default_timeout() -> int:
    value = int(os.environ.get("ORCAN_EXECUTOR_TIMEOUT_SECONDS", "1800"))
    if not 1 <= value <= 21600:
        raise ValueError("Default timeout must be between 1 and 21600 seconds")
    return value


def redis_memory_mb() -> int:
    value = int(os.environ.get("ORCAN_EXECUTOR_REDIS_MEMORY_MB", "128"))
    if not 32 <= value <= 4096:
        raise ValueError("Redis memory limit must be between 32 and 4096 MiB")
    return value


def visibility_timeout() -> int:
    value = int(os.environ.get("ORCAN_EXECUTOR_VISIBILITY_TIMEOUT_SECONDS", "86400"))
    if not 22200 <= value <= 86400:
        raise ValueError("Visibility timeout must be between 22200 and 86400 seconds")
    return value


def effective() -> dict:
    return {
        "split_lanes": os.environ.get("ORCAN_EXECUTOR_SPLIT_LANES", "0") == "1",
        "max_pending": max_pending(),
        "max_running": max_running(),
        "timeout_seconds": default_timeout(),
        "retention_seconds": retention_seconds(),
        "redis_memory_mb": redis_memory_mb(),
        "visibility_timeout_seconds": visibility_timeout(),
        "history_days": HISTORY_DAYS,
        "history_limit": HISTORY_LIMIT,
        "source": "process environment with built-in defaults; JSON is materialized by orcan sync",
    }
