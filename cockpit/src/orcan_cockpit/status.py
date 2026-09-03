"""Pure status-line data + formatting: git branch, CPU/RAM/clock, and the
bottom/top bar assembly. Deliberately stdlib-only (no Textual/orcan.*
import), so it is directly unit-testable on
the host.

CPU/RAM read the same /proc sources tmux's own pane-border-right.sh used to
(before that got trimmed from status.conf as redundant with the cockpit's
own top bar — see that file's header comment) — kept as plain stdlib reads
here rather than shelling out to the (now tmux-unused, still-on-disk)
script, since Python can read /proc directly.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from typing import Literal

Tier = Literal["full", "compact", "minimal"]


def tier_for_width(columns: int) -> Tier:
    """Terminal-column breakpoints, not browser viewport ones — see plan
    doc's "Layout target" table. Applied via CSS classes on MainScreen
    (app.py's on_resize), not media queries."""
    if columns >= 120:
        return "full"
    if columns >= 90:
        return "compact"
    return "minimal"


def git_branch(root: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", root, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=0.5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    branch = result.stdout.strip()
    if branch != "HEAD":
        return branch
    # Detached HEAD — same fallback status-right.sh uses.
    try:
        result = subprocess.run(
            ["git", "-C", root, "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=0.5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip()


def read_loadavg() -> str | None:
    try:
        with open("/proc/loadavg") as f:
            return f"{float(f.read().split()[0]):.1f}"
    except (OSError, ValueError, IndexError):
        return None


def read_mem_percent() -> str | None:
    try:
        fields: dict[str, int] = {}
        with open("/proc/meminfo") as f:
            for line in f:
                key, _, rest = line.partition(":")
                parts = rest.strip().split()
                if parts:
                    fields[key] = int(parts[0])
        total = fields.get("MemTotal")
        avail = fields.get("MemAvailable")
        if not total or avail is None:
            return None
        return f"{round((total - avail) / total * 100)}%"
    except (OSError, ValueError):
        return None


def now_hhmm() -> str:
    return datetime.now().strftime("%H:%M")


def format_status_line(
    *,
    tier: Tier,
    workspace: str | None,
    branch: str,
    session: str | None,
    breadcrumb: str = "",
) -> str:
    """The bottom bar: workspace identity + optional tmux breadcrumb.

    CPU/RAM/clock live in the top bar (format_top_bar_right) and the problems
    🔔 lives in the rail (rail.py) exclusively.
    """
    parts = [workspace or "(no workspace)"]
    if tier == "full" and branch:
        parts.append(f"⎇ {branch}")
    if tier == "full" and session:
        parts.append(f"tmux:{session}")
    if tier == "full" and breadcrumb:
        parts.append(breadcrumb)
    return "  ·  ".join(parts)


def format_top_bar_right(*, cpu: str | None, mem: str | None, clock: str) -> str:
    parts = []
    if cpu:
        parts.append(f"load {cpu}")
    if mem:
        parts.append(f"mem {mem}")
    parts.append(clock)
    return "  ·  ".join(parts)
