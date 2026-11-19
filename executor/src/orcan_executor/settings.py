"""Instance-local runtime settings. No dotenv or project secrets are loaded."""

import os
import re
from pathlib import Path

from .plugin import fields

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


def plugin_integer(name: str, label: str, *, default: int | None = None) -> int:
    rule = fields()[name]
    value = int(os.environ.get(rule["env"], str(rule["default"] if default is None else default)))
    if not rule["minimum"] <= value <= rule["maximum"]:
        raise ValueError(f"{label} must be between {rule['minimum']} and {rule['maximum']}")
    return value


def retention_seconds() -> int:
    return plugin_integer("retention_seconds", "Retention")


def minimum_free_mb() -> int:
    value = int(os.environ.get("ORCAN_EXECUTOR_MIN_FREE_MB", "1024"))
    if not 1 <= value <= 1048576:
        raise ValueError("Minimum free space must be between 1 and 1048576 MiB")
    return value


def storage_limit_mb(name: str) -> int:
    if name not in {"log_limit_mb", "artifact_limit_mb", "detail_budget_mb", "worktree_budget_mb"}:
        raise ValueError("Unknown executor storage limit: " + name)
    return plugin_integer(name, name)


def max_pending() -> int:
    return plugin_integer("max_pending", "Pending limit")


def max_running() -> int:
    return plugin_integer("max_running", "Running limit")


def default_timeout() -> int:
    return plugin_integer("timeout_seconds", "Default timeout")


def redis_memory_mb() -> int:
    return plugin_integer("redis_memory_mb", "Redis memory limit")


def visibility_timeout() -> int:
    return plugin_integer("visibility_timeout_seconds", "Visibility timeout")


def worker_count() -> int:
    default = 1 if split_lanes() else fields()["workers"]["default"]
    value = plugin_integer("workers", "Worker count", default=default)
    if split_lanes() and value != 1:
        raise ValueError("Worker count must be 1 when split lanes are enabled")
    return value


def split_lanes() -> bool:
    rule = fields()["split_lanes"]
    return os.environ.get(rule["env"], str(int(rule["default"]))) == "1"


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
        "source": "process environment with bundled Redis plugin defaults; host launch resolves JSON settings",
    }
