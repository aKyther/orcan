#!/usr/bin/env python3
"""Core defaults and compatibility projections of bundled plugin settings."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "docker/rootfs/usr/local/lib"))
from orcan.plugin_registry import catalog

TMUX_DEFAULTS: dict[str, object] = {
    "initial_windows": 3,
    "history_limit": 20000,
    "window_prefix": "tab",
}

# Compatibility projection for init and the Studio bridge; plugin metadata owns values.
TTYD_DEFAULTS: dict[str, object] = {
    key: rule["default"]
    for entry in catalog() if entry["id"] == "ttyd"
    for key, rule in entry["fields"].items() if key != "authentication"
}

RESOURCE_DEFAULTS: dict[str, object] = {
    "cpus": 2,
    "memory": "4g",
    "shm_size": "512m",
    "tmpfs_size": "512m",
}

PROCESS_DEFAULTS: dict[str, int] = {"nofile": 65536, "nproc": 65536}
