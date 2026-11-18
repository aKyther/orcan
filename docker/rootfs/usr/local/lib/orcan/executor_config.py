"""Shared, strict executor settings for host configuration and runtime tools."""

from .plugin_registry import catalog
from .plugin_registry import resolve as resolve_plugins

_FIELDS = next(entry["fields"] for entry in catalog() if entry["id"] == "redis")
# Compatibility projections for callers of the original executor settings API.
DEFAULTS = {key: rule["default"] for key, rule in _FIELDS.items() if key != "port"}
LIMITS = {
    key: (rule["minimum"], rule["maximum"])
    for key, rule in _FIELDS.items() if key in DEFAULTS and rule["type"] == "integer"
}
ENVIRONMENT = {key: _FIELDS[key]["env"] for key in DEFAULTS}


def resolve(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) - DEFAULTS.keys():
        raise ValueError("executor supports: " + ", ".join(DEFAULTS))
    resolved = resolve_plugins({"executor": value})["redis"]
    return {key: resolved[key] for key in DEFAULTS}
