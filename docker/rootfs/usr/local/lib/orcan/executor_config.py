"""Shared, strict executor settings for host configuration and runtime tools."""

DEFAULTS = {
    "split_lanes": False,
    "workers": 1,
    "max_pending": 100,
    "max_running": 2,
    "timeout_seconds": 1800,
    "retention_seconds": 3600,
    "redis_memory_mb": 128,
    "visibility_timeout_seconds": 86400,
}
LIMITS = {
    "workers": (1, 3),
    "max_pending": (1, 10000),
    "max_running": (1, 3),
    "timeout_seconds": (1, 21600),
    "retention_seconds": (60, 86400),
    "redis_memory_mb": (32, 4096),
    "visibility_timeout_seconds": (22200, 86400),
}
ENVIRONMENT = {
    "workers": "ORCAN_EXECUTOR_WORKERS",
    "split_lanes": "ORCAN_EXECUTOR_SPLIT_LANES",
    "max_pending": "ORCAN_EXECUTOR_MAX_PENDING",
    "max_running": "ORCAN_EXECUTOR_MAX_RUNNING",
    "timeout_seconds": "ORCAN_EXECUTOR_TIMEOUT_SECONDS",
    "retention_seconds": "ORCAN_EXECUTOR_RETENTION_SECONDS",
    "redis_memory_mb": "ORCAN_EXECUTOR_REDIS_MEMORY_MB",
    "visibility_timeout_seconds": "ORCAN_EXECUTOR_VISIBILITY_TIMEOUT_SECONDS",
}


def resolve(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) - DEFAULTS.keys():
        raise ValueError("executor supports: " + ", ".join(DEFAULTS))
    result = DEFAULTS | value
    if type(result["split_lanes"]) is not bool:
        raise ValueError("executor.split_lanes must be a boolean")
    for key, (minimum, maximum) in LIMITS.items():
        if type(result[key]) is not int or not minimum <= result[key] <= maximum:
            raise ValueError(f"executor.{key} must be an integer from {minimum} to {maximum}")
    if result["split_lanes"] and result["workers"] != 1:
        raise ValueError("executor.workers must be 1 when split_lanes is enabled")
    return result
