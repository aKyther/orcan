"""Ephemeral cockpit state kept for reconnects within one container run."""

from __future__ import annotations

import os
import tempfile
import json
from pathlib import Path

_DEFAULT_STATE_PATH = Path("/tmp/orcan-cockpit-last-session")
_MAX_RECENT_SESSIONS = 6


def state_path() -> Path:
    override = os.environ.get("ORCAN_COCKPIT_STATE_PATH")
    return Path(override) if override else _DEFAULT_STATE_PATH


def recent_sessions_path() -> Path:
    """Small sibling state file; recent choices are runtime-local only."""
    override = os.environ.get("ORCAN_COCKPIT_RECENT_SESSIONS_PATH")
    return Path(override) if override else state_path().with_name(
        f"{state_path().name}-recent"
    )


def read_last_session() -> str | None:
    """Return the last attached tmux session, ignoring stale/broken state."""
    try:
        value = state_path().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not value or "\n" in value or "\x00" in value or len(value) > 256:
        return None
    return value


def read_recent_sessions() -> list[str]:
    """Most-recent workspace sessions, newest first; ignore corrupt state."""
    try:
        values = json.loads(recent_sessions_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(values, list):
        return []
    recent: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value or "\n" in value or "\x00" in value:
            continue
        if value not in recent:
            recent.append(value)
        if len(recent) >= _MAX_RECENT_SESSIONS:
            break
    return recent


def _atomic_write(path: Path, content: str) -> None:
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
            handle.write(content)
        os.replace(temporary, path)
    except OSError:
        if temporary is not None:
            try:
                Path(temporary).unlink()
            except OSError:
                pass


def remember_session(session: str) -> None:
    """Atomically remember *session*; failure must never block an attach."""
    _atomic_write(state_path(), f"{session}\n")
    recent = [session, *(value for value in read_recent_sessions() if value != session)]
    _atomic_write(recent_sessions_path(), json.dumps(recent[:_MAX_RECENT_SESSIONS]) + "\n")
