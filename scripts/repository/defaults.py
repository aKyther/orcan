#!/usr/bin/env python3
"""Single source of truth for tmux / ttyd / resource defaults.

Consumed by apply-config.py (runtime config + synthesized fallback),
config-wizard.py (`create_fresh`) and settings-wizard.py. Keeping the
literals here stops the four copies from drifting apart.
"""

from __future__ import annotations

TMUX_DEFAULTS: dict[str, object] = {
    "initial_windows": 3,
    "window_prefix": "tab",
}

TTYD_DEFAULTS: dict[str, object] = {
    "port": 7681,
    "host_port": 7681,
    # Host publish address — default all interfaces (LAN / VM).
    "bind": "0.0.0.0",
    "font_size": 14,
    "font_family": "Menlo, Monaco, 'Courier New', monospace",
    "theme": "dark",
    "ping_interval": 20,
}

RESOURCE_DEFAULTS: dict[str, object] = {
    "cpus": 2,
    "memory": "4g",
    "shm_size": "512m",
    "tmpfs_size": "512m",
}
