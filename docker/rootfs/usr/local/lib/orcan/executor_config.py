"""Shared, strict executor settings for host configuration and runtime tools."""

DEFAULTS = {
    "split_lanes": False,
    "max_pending": 100,
    "max_running": 2,
    "timeout_seconds": 1800,
    "retention_seconds": 3600,
}
LIMITS = {
    "max_pending": (1, 10000),
    "max_running": (1, 3),
    "timeout_seconds": (1, 21600),
    "retention_seconds": (60, 86400),
}
ENVIRONMENT = {
    "split_lanes": "ORCAN_EXECUTOR_SPLIT_LANES",
    "max_pending": "ORCAN_EXECUTOR_MAX_PENDING",
    "max_running": "ORCAN_EXECUTOR_MAX_RUNNING",
    "timeout_seconds": "ORCAN_EXECUTOR_TIMEOUT_SECONDS",
    "retention_seconds": "ORCAN_EXECUTOR_RETENTION_SECONDS",
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
    return result
