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
from pathlib import Path
from typing import Any

from libtmux import Server
from libtmux.exc import LibTmuxException

from orcan.workspaces import compact_hints, iter_workspaces, load_config
from orcan_cockpit.session_glance import format_glance, glance_lines
from orcan_cockpit.status import git_branch

# One shared connection to the default tmux server/socket (same one
# cursor-tmux-workspace-attach and the rest of orcan target) — not a new
# server per call.
_tmux_server = Server()


def session_is_live(session: str) -> bool:
    try:
        return _tmux_server.has_session(session)
    except LibTmuxException:
        return False


def project_git_label(project: dict[str, Any]) -> str:
    """One compact token for a single project entry: bare name if it isn't
    a git repo, `⎇ branch` if it is, `⎇+ branch (worktree)` if it's a
    *linked* worktree rather than the repo's main checkout.

    `.git` as a directory vs. a file is the cheap, subprocess-free way to
    tell those two apart (a linked worktree's `.git` is a one-line file
    pointing at the real gitdir elsewhere — see `git worktree add`/
    `scripts/repository/git_worktrees.py`, which orcan already manages
    worktrees through). Distinguishing it matters operationally: a worktree
    shares history with its parent clone and can't be casually deleted or
    moved on its own the way a plain clone can.
    """
    name = str(project.get("name") or project.get("alias") or "?").strip() or "?"
    path = str(project.get("path") or "").strip()
    if not path:
        return name
    git_path = Path(path) / ".git"
    if git_path.is_file():
        branch = git_branch(path)
        return f"⎇+ {branch} (worktree)" if branch else f"{name} (worktree)"
    if git_path.is_dir():
        branch = git_branch(path)
        return f"⎇ {branch}" if branch else name
    return name


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
                "repo_count": len(ws["projects"]),
                # Raw project list (name/path), not a pre-joined names
                # string: git status (below) is only ever computed for the
                # `i`-expanded row, not on every 5s refresh_rows() poll of
                # every workspace — each check is a real `git` subprocess
                # call, wasteful to run for rows nobody is looking at.
                "projects": ws["projects"],
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

from textual import events  # noqa: E402
from textual.app import ComposeResult  # noqa: E402
from textual.widget import Widget  # noqa: E402
from textual.widgets import Label, ListItem, ListView, Static  # noqa: E402

# ●/○/▸ have no other explanation anywhere in the app (not even the
# shortcuts modal) — this is the first thing a user sees, so the legend is
# a permanent caption under the list rather than a hover-only tooltip
# (which a non-mouse/native-terminal session might never trigger).
# \[ escapes the literal bracket — Static defaults to markup=True, and an
# unescaped [i] parses as an (unclosed) Rich style tag that silently drops
# the letter from the render (same class of bug found and fixed in
# activity.py's hint line this session — confirmed with Text.from_markup()).
# Two lines, not one: the full text is 44 cells, wider than this card's
# ~30-col usable width — on one line "[i] expand" silently clipped off the
# end entirely (found while verifying the feature it's advertising).
LEGEND = "● live   ○ new   ▸ attached\n" r"\[i] expand"

# Kept fresh enough to notice a session someone killed elsewhere without
# feeling like a busy-poll — this is cosmetic status (● live / ○ new), not
# anything time-sensitive.
_REFRESH_INTERVAL_S = 5.0
_GLANCE_EMPTY = "↑ Enter to attach"


class WorkspaceList(Widget):
    """Left column: persistent workspace list — like `tmux list-sessions`,
    always visible, not a one-shot picker screen you navigate away from.
    Selecting a row tells the app to (re)attach the center terminal to it.

    One line per row by default — with many workspaces configured, a
    two-line-per-item list runs out of room fast; ListView is a
    VerticalScroll under the hood, so it already scrolls/shows a scrollbar
    once rows overflow the card's height, no extra work needed for that.
    `i` toggles a second, muted line per row (root path + per-project git
    status — plain name if not a git repo, `⎇ branch` if it is, `⎇+ branch
    (worktree)` if it's a linked worktree rather than the main checkout;
    see project_git_label() — just enough to identify a workspace, not a
    full status readout)."""

    can_focus = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.rows: list[dict[str, Any]] = []
        self.active_session: str | None = None
        self._expanded = False

    def compose(self) -> ComposeResult:
        yield ListView(id="workspace-list")
        yield Static(format_glance([], empty_hint=_GLANCE_EMPTY), id="workspace-glance")
        yield Static(LEGEND, id="workspace-legend")

    def on_mount(self) -> None:
        self.refresh_rows()
        self.set_interval(_REFRESH_INTERVAL_S, self.refresh_rows)

    def on_key(self, event: events.Key) -> None:
        # ListView (the actual focus target — see app.py's on_mount) doesn't
        # bind "i", so this bubbles up to us unstopped.
        if event.key == "i":
            self._expanded = not self._expanded
            self._render_rows()
            event.stop()

    def set_active_session(self, session: str | None) -> None:
        """Called by MainScreen once a workspace is actually attached — a
        different thing from ListView's own keyboard-cursor `index`
        (which row you're currently browsing), so tracked separately."""
        self.active_session = session
        self._render_rows()
        self._update_glance()

    def refresh_rows(self) -> None:
        try:
            self.rows = list_workspace_rows()
        except (OSError, ValueError) as exc:
            self.notify(f"Error reading config: {exc}", severity="error")
            self.rows = []
        self._render_rows()
        self._update_glance()

    def _render_rows(self) -> None:
        list_view = self.query_one("#workspace-list", ListView)
        selected = list_view.index
        list_view.clear()
        for row in self.rows:
            dot = "●" if row["live"] else "○"
            is_active = row["session"] == self.active_session
            marker = "▸" if is_active else " "
            text = f"{marker}{dot} {row['name']}"
            if self._expanded:
                repos = f"{row['repo_count']} repo" + ("" if row["repo_count"] == 1 else "s")
                # git status per project only gets computed here, for the
                # expanded row actually being rendered — see the comment on
                # "projects" in list_workspace_rows() for why (a real `git`
                # subprocess per project, per row, on every 5s poll would be
                # wasted work for rows nobody has expanded).
                labels = [project_git_label(p) for p in row["projects"] if isinstance(p, dict)]
                if labels:
                    repos += f": {', '.join(labels)}"
                # Two separate lines, not one "root · repos" line: ListView's
                # own DEFAULT_CSS sets overflow:hidden on ListItem, and this
                # card is only ~30 cols wide — a real workspace root like
                # /home/developer/workspaces/dev-ux (34 chars) already fills
                # that on its own, so appending git status after it on the
                # same line silently clipped the whole thing off-screen
                # (confirmed via Textual's own item.size — width demanded
                # was 53, box was 30). ~ for $HOME buys back some of that
                # width too. Dimmed via markup, not a second CSS rule — this
                # is plain text glued into a single Label's renderable, not
                # a separate widget a stylesheet selector could target.
                home = os.path.expanduser("~")
                root = row["root"]
                if home and root.startswith(home):
                    root = "~" + root[len(home):]
                text += f"\n   [#64748b]{root}[/]"
                text += f"\n   [#64748b]{repos}[/]"
            item = ListItem(Label(text))
            if is_active:
                item.add_class("active-workspace")
            list_view.append(item)
        if selected is not None and selected < len(self.rows):
            list_view.index = selected

    def _highlighted_row(self) -> dict[str, Any] | None:
        list_view = self.query_one("#workspace-list", ListView)
        index = list_view.index
        if index is None or not (0 <= index < len(self.rows)):
            return None
        return self.rows[index]

    def _update_glance(self) -> None:
        row = self._highlighted_row()
        body = self.query_one("#workspace-glance", Static)
        if row is None:
            body.update(format_glance([], empty_hint=_GLANCE_EMPTY))
            return
        lines = glance_lines(
            row["session"],
            row["root"],
            live=bool(row["live"]),
            projects=row.get("projects"),
        )
        body.update(format_glance(lines, empty_hint=_GLANCE_EMPTY))

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        self._update_glance()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        index = event.list_view.index
        if index is None or not (0 <= index < len(self.rows)):
            return
        self.app.select_workspace(self.rows[index])  # type: ignore[attr-defined]

    def action_quit_app(self) -> None:
        self.app.exit()
