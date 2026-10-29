"""Small validated runtime budgets; no heap/disk reservation or memory scans."""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULTS = {
    "pty_read_bytes": 262144,
    "pty_read_ms": 8,
    "pty_chunk_bytes": 16384,
    "peek_chars": 1200,
}
BOUNDS = {
    "pty_read_bytes": (4096, 1048576),
    "pty_read_ms": (1, 50),
    "pty_chunk_bytes": (4096, 65536),
    "peek_chars": (256, 8192),
}


def limits() -> dict[str, int]:
    result = DEFAULTS.copy()
    try:
        with Path(
            os.environ.get("ORCAN_CONFIG", "/etc/orcan/config.json")
        ).open() as source:
            content = source.read(1024 * 1024 + 1)
        if len(content) > 1024 * 1024:
            return result
        configured = json.loads(content).get("cockpit", {})
        if not isinstance(configured, dict):
            return result
        for key, (low, high) in BOUNDS.items():
            value = configured.get(key, result[key])
            if type(value) is int and low <= value <= high:
                result[key] = value
    except (OSError, ValueError, AttributeError):
        pass
    return result
