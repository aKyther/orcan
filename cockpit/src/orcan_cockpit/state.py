"""Ephemeral cockpit state kept for reconnects within one container run."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_DEFAULT_STATE_PATH = Path("/tmp/orcan-cockpit-last-session")


def state_path() -> Path:
    override = os.environ.get("ORCAN_COCKPIT_STATE_PATH")
    return Path(override) if override else _DEFAULT_STATE_PATH


def read_last_session() -> str | None:
    """Return the last attached tmux session, ignoring stale/broken state."""
    try:
        value = state_path().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not value or "\n" in value or "\x00" in value or len(value) > 256:
        return None
    return value


def remember_session(session: str) -> None:
    """Atomically remember *session*; failure must never block an attach."""
    path = state_path()
    temporary: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(f"{session}\n")
        os.replace(temporary, path)
    except OSError:
        if temporary is not None:
            try:
                Path(temporary).unlink()
            except OSError:
                pass
