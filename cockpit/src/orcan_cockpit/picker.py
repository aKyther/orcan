"""Workspace picker: pure listing/formatting helpers (no Textual import
needed to use them) plus the interactive Textual screen and the non-tty
fallback menu that both sit on top of them.

Data source is the same `orcan.workspaces` module the old bash
`agent-launcher` reached via the `orcan-workspaces` CLI, and that
`orcan-context-status` already uses — no workspace-discovery logic is
duplicated here. (orcan.workspaces is vendored/stdlib-only — see cli.py for
where /usr/local/lib is added to sys.path.)
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

from libtmux import Server
from libtmux.exc import LibTmuxException

from orcan.workspaces import compact_hints, iter_workspaces, load_config

# One shared connection to the default tmux server/socket (same one
# cursor-tmux-workspace-attach and the rest of orcan target) — not a new
# server per call.
_tmux_server = Server()


def session_is_live(session: str) -> bool:
    try:
        return _tmux_server.has_session(session)
    except LibTmuxException:
        return False


def list_workspace_rows(config_path: str | None = None) -> list[dict[str, Any]]:
    cfg = load_config(config_path)
    rows: list[dict[str, Any]] = []
    for ws in iter_workspaces(cfg):
        rows.append(
            {
                "name": ws["name"],
                "root": ws["root"],
                "session": ws["tmux_session"],
                "hints": compact_hints(ws),
                "live": session_is_live(ws["tmux_session"]),
            }
        )
    return rows


def format_fallback_menu(rows: list[dict[str, Any]]) -> str:
    lines = ["orcan workspaces", "─" * 28]
    if not rows:
        lines.append("(no workspaces configured)")
    else:
        for i, row in enumerate(rows, start=1):
            status = "[tmux live]" if row["live"] else "[new]"
            lines.append(f" {i}) {row['name']:<16} {status}")
            lines.append(f"    session: {row['session']}")
            lines.append(f"    {row['root']}")
            if row["hints"]:
                lines.append(f"    context: {row['hints']}")
    lines.append("─" * 28)
    lines.append("q) quit")
    return "\n".join(lines) + "\n"


def bootstrap_workspace(row: dict[str, Any]) -> subprocess.CompletedProcess:
    """Create/validate the tmux session without attaching (ORCAN_TMUX_ATTACH=0,
    the same escape hatch tests/smoke/test-container.sh already relies on) —
    reuses cursor-tmux-workspace-attach's bootstrap logic rather than
    reimplementing session/window/env-var setup in Python."""
    return subprocess.run(
        ["cursor-tmux-workspace-attach", row["session"], row["root"], row["name"]],
        env={**os.environ, "ORCAN_TMUX_ATTACH": "0"},
        check=False,
    )


def run_fallback_menu() -> int:
    """Non-tty entry point (piped stdin — smoke tests, scripted use). Prints
    the same data the interactive picker shows, minus the live TUI: 'q'/EOF
    exits, a number bootstraps that workspace's tmux session (no attach —
    there is no pty here to attach a real terminal into)."""
    while True:
        try:
            rows = list_workspace_rows()
        except (OSError, ValueError) as exc:
            print(f"Error reading config: {exc}", file=sys.stderr)
            return 1
        print(format_fallback_menu(rows), end="")
        line = sys.stdin.readline()
        if not line:
            return 0
        choice = line.strip().lower()
        if choice in ("q", ""):
            return 0
        if choice.isdigit():
            index = int(choice) - 1
            if 0 <= index < len(rows):
                bootstrap_workspace(rows[index])
                continue
        print(f"Enter 1-{len(rows)} or q.", file=sys.stderr)


# --- Interactive Textual widget --------------------------------------------
# Imported lazily by orcan_cockpit.app (only reached on a real tty) so the
# non-tty fallback path above never pays for a Textual import it doesn't need.

from textual.app import ComposeResult  # noqa: E402
from textual.widget import Widget  # noqa: E402
from textual.widgets import Label, ListItem, ListView  # noqa: E402

# Kept fresh enough to notice a session someone killed elsewhere without
# feeling like a busy-poll — this is cosmetic status (● live / ○ new), not
# anything time-sensitive.
_REFRESH_INTERVAL_S = 5.0


class WorkspaceList(Widget):
    """Left column: persistent workspace list — like `tmux list-sessions`,
    always visible, not a one-shot picker screen you navigate away from.
    Selecting a row tells the app to (re)attach the center terminal to it.

    One line per row (not two) — with many workspaces configured, a
    two-line-per-item list runs out of room fast; ListView is a
    VerticalScroll under the hood, so it already scrolls/shows a scrollbar
    once rows overflow the card's height, no extra work needed for that."""

    can_focus = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.rows: list[dict[str, Any]] = []
        self.active_session: str | None = None

    def compose(self) -> ComposeResult:
        yield ListView(id="workspace-list")

    def on_mount(self) -> None:
        self.refresh_rows()
        self.set_interval(_REFRESH_INTERVAL_S, self.refresh_rows)

    def set_active_session(self, session: str | None) -> None:
        """Called by MainScreen once a workspace is actually attached — a
        different thing from ListView's own keyboard-cursor `index`
        (which row you're currently browsing), so tracked separately."""
        self.active_session = session
        self._render_rows()

    def refresh_rows(self) -> None:
        try:
            self.rows = list_workspace_rows()
        except (OSError, ValueError) as exc:
            self.notify(f"Error reading config: {exc}", severity="error")
            self.rows = []
        self._render_rows()

    def _render_rows(self) -> None:
        list_view = self.query_one("#workspace-list", ListView)
        selected = list_view.index
        list_view.clear()
        for row in self.rows:
            dot = "●" if row["live"] else "○"
            is_active = row["session"] == self.active_session
            marker = "▸" if is_active else " "
            item = ListItem(Label(f"{marker}{dot} {row['name']}"))
            if is_active:
                item.add_class("active-workspace")
            list_view.append(item)
        if selected is not None and selected < len(self.rows):
            list_view.index = selected

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        index = event.list_view.index
        if index is None or not (0 <= index < len(self.rows)):
            return
        self.app.select_workspace(self.rows[index])  # type: ignore[attr-defined]

    def action_quit_app(self) -> None:
        self.app.exit()
