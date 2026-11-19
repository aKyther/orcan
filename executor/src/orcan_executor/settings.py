"""Instance-local runtime settings. No dotenv or project secrets are loaded."""

import os
import re
from pathlib import Path

HISTORY_DAYS = 30
HISTORY_LIMIT = 10000
QUEUE_WAIT_TIMEOUT_SECONDS = 30 * 60


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


def artifact_root() -> Path:
    """External payload storage only; never relocate SQLite or run.lock files."""
    raw = os.environ.get("ORCAN_STORAGE_ROOT", "")
    if not raw:
        return state_dir() / "jobs"
    root = Path(raw)
    if not root.is_absolute() or not root.is_dir() or root.resolve() != root:
        raise OSError("Configured artifact storage is unavailable or not canonical")
    anchor = Path(os.environ.get("ORCAN_STORAGE_MOUNT") or root)
    if not root.is_relative_to(anchor):
        raise OSError("Artifact path is outside its configured mountpoint")
    if os.environ.get("ORCAN_STORAGE_REQUIRE_MOUNT", "1") == "1" and not anchor.is_mount():
        raise OSError("Configured artifact storage is not mounted; local fallback is disabled")
    current = root
    for part in ("orcan", namespace(), "executor"):
        current = current / part
        if current.is_symlink():
            raise OSError("Artifact namespace must not contain symlinks")
    return current


def artifact_directory(job: dict) -> Path:
    """Locate local legacy/receipt payloads or payloads on the current external root."""
    directory = (
        Path(job["report"]).parent
        if job.get("report")
        else artifact_root() / job["id"] / str(job["attempts"])
    )
    # Local metadata/legacy evidence remains readable even when external storage is offline.
    if directory.resolve().is_relative_to(state_dir() / "jobs" / job["id"]):
        return directory
    if directory.resolve().is_relative_to(artifact_root() / job["id"]):
        return directory
    raise ValueError("Artifact directory is outside this job's configured storage")


def artifact_job_directory(job: dict) -> Path:
    directory = artifact_directory(job)
    root = state_dir() / "jobs" / job["id"]
    if directory == root:
        return root
    if directory.parent == root or directory.parent == artifact_root() / job["id"]:
        return directory.parent
    raise ValueError("Invalid job artifact directory")


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


def minimum_free_mb() -> int:
    value = int(os.environ.get("ORCAN_EXECUTOR_MIN_FREE_MB", "1024"))
    if not 1 <= value <= 1048576:
        raise ValueError("Minimum free space must be between 1 and 1048576 MiB")
    return value


def storage_limit_mb(name: str) -> int:
    defaults = {
        "log_limit_mb": 16,
        "artifact_limit_mb": 64,
        "detail_budget_mb": 1024,
        "worktree_budget_mb": 8192,
    }
    value = int(os.environ.get("ORCAN_EXECUTOR_" + name.upper(), str(defaults[name])))
    if not 1 <= value <= 1048576:
        raise ValueError(name + " must be between 1 and 1048576 MiB")
    return value


def max_pending() -> int:
    value = int(os.environ.get("ORCAN_EXECUTOR_MAX_PENDING", "100"))
    if not 1 <= value <= 10000:
        raise ValueError("Pending limit must be between 1 and 10000")
    return value


def max_running() -> int:
    value = int(os.environ.get("ORCAN_EXECUTOR_MAX_RUNNING", "3"))
    if not 1 <= value <= 10:
        raise ValueError("Running limit must be between 1 and 10")
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


def worker_count() -> int:
    value = int(os.environ.get("ORCAN_EXECUTOR_WORKERS", "1" if split_lanes() else "3"))
    if not 1 <= value <= 10:
        raise ValueError("Worker count must be between 1 and 10")
    if split_lanes() and value != 1:
        raise ValueError("Worker count must be 1 when split lanes are enabled")
    return value


def split_lanes() -> bool:
    return os.environ.get("ORCAN_EXECUTOR_SPLIT_LANES", "0") == "1"


def execution_lane(lane: str) -> str:
    return lane if split_lanes() else "default"


def effective() -> dict:
    return {
        "split_lanes": split_lanes(),
        "workers": worker_count(),
        "max_pending": max_pending(),
        "max_running": max_running(),
        "timeout_seconds": default_timeout(),
        "queue_wait_timeout_seconds": QUEUE_WAIT_TIMEOUT_SECONDS,
        "retention_seconds": retention_seconds(),
        "minimum_free_mb": minimum_free_mb(),
        **{
            key: storage_limit_mb(key)
            for key in (
                "log_limit_mb",
                "artifact_limit_mb",
                "detail_budget_mb",
                "worktree_budget_mb",
            )
        },
        "redis_memory_mb": redis_memory_mb(),
        "visibility_timeout_seconds": visibility_timeout(),
        "history_days": HISTORY_DAYS,
        "history_limit": HISTORY_LIMIT,
        "scheduling": "repo_round_robin_per_lane",
        "source": "process environment with built-in defaults; host launch resolves JSON settings",
    }
