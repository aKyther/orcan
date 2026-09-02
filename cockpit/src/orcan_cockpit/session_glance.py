"""Session glance — 2–3 short lines about what is alive in a workspace.

Stdlib-only so host tests can
lock formatting without Textual. Used by the workspace picker when a row is
highlighted: pending (+age), worktrees / idle-or-brief, live pane commands.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

_MAX_LINES = 3
_MAX_PANE_CMDS = 3
_TMUX_TIMEOUT_S = 2
# Under this, session activity is "active" rather than "idle Xm".
_ACTIVE_WINDOW_S = 120


def format_age(timestamp: float | None, *, now: float | None = None) -> str:
    if timestamp is None:
        return ""
    seconds = max(0, int((time.time() if now is None else now) - timestamp))
    if seconds < 60:
        return "now"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def pane_commands(session: str) -> list[str]:
    """Unique pane commands in *session* (active window), order preserved."""
    try:
        out = subprocess.check_output(
            [
                "tmux",
                "list-panes",
                "-t",
                f"={session}:",
                "-F",
                "#{pane_current_command}",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=_TMUX_TIMEOUT_S,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []
    seen: set[str] = set()
    cmds: list[str] = []
    for line in out.splitlines():
        cmd = line.strip()
        if not cmd or cmd in seen:
            continue
        seen.add(cmd)
        cmds.append(cmd)
        if len(cmds) >= _MAX_PANE_CMDS:
            break
    return cmds


def linked_worktree_count(projects: list[Any] | None) -> int:
    """How many projects are linked git worktrees (``.git`` is a file)."""
    count = 0
    for project in projects or []:
        if not isinstance(project, dict):
            continue
        path = str(project.get("path") or "").strip()
        if path and (Path(path) / ".git").is_file():
            count += 1
    return count


def session_activity_line(session: str, *, now: float | None = None) -> str:
    """``active`` / ``idle 40m`` from tmux ``#{session_activity}``, else ````."""
    try:
        out = subprocess.check_output(
            [
                "tmux",
                "display-message",
                "-p",
                "-t",
                f"={session}:",
                "#{session_activity}",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=_TMUX_TIMEOUT_S,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""
    raw = out.strip()
    if not raw.isdigit():
        return ""
    activity_ts = float(raw)
    clock = time.time() if now is None else now
    age_s = max(0, int(clock - activity_ts))
    if age_s < _ACTIVE_WINDOW_S:
        return "active"
    age = format_age(activity_ts, now=clock)
    return f"idle {age}" if age else "active"


def brief_activity_line(workspace_root: Path, *, now: float | None = None) -> str:
    """``brief 2h`` from ``.orcan/session-brief.md`` mtime when present."""
    brief = workspace_root / ".orcan" / "session-brief.md"
    if not brief.is_file():
        return ""
    try:
        mtime = brief.stat().st_mtime
    except OSError:
        return ""
    age = format_age(mtime, now=now)
    return f"brief {age}" if age else ""


def _visibility_line(
    session: str | None,
    root: Path | None,
    *,
    live: bool,
    projects: list[Any] | None,
    now: float | None = None,
) -> str:
    """Worktree count + idle/brief."""
    parts: list[str] = []
    wt = linked_worktree_count(projects)
    if wt:
        parts.append(f"{wt} wt")

    if live and session:
        activity = session_activity_line(session, now=now)
        if activity:
            parts.append(activity)
    elif root is not None:
        brief = brief_activity_line(root, now=now)
        if brief:
            parts.append(brief)

    if parts:
        return " · ".join(parts)

    return ""


def glance_lines(
    session: str | None,
    workspace_root: str | Path | None,
    *,
    live: bool,
    projects: list[Any] | None = None,
    now: float | None = None,
) -> list[str]:
    """Up to three glance lines for a workspace row.

    Order: worktrees/idle-or-brief → panes when *live*.
    """
    lines: list[str] = []
    root = Path(workspace_root) if workspace_root else None

    visibility = _visibility_line(
        session, root, live=live, projects=projects, now=now
    )
    if visibility:
        lines.append(visibility)

    if live and session:
        cmds = pane_commands(session)
        if cmds:
            lines.append("panes: " + ", ".join(cmds))

    return lines[:_MAX_LINES]


def format_glance(lines: list[str], *, empty_hint: str = "Enter to attach") -> str:
    """Markup-ready glance body for a Static (dim when only the empty hint)."""
    if not lines:
        return f"[#64748b]{empty_hint}[/]"
    # Titles and pane text come from workspace state and may contain
    # Rich/Textual markup delimiters. Escape opening brackets so user text
    # cannot become an accidental style tag (or break rendering altogether).
    def escape_markup(text: str) -> str:
        return text.replace("\\", "\\\\").replace("[", "\\[")

    return "\n".join(f"[#94a3b8]{escape_markup(line)}[/]" for line in lines)
