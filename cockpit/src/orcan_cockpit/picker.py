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


def live_session_names() -> set[str]:
    """All live tmux session names in one query.

    Prefer this over N× ``has_session`` on the 5s workspace-list poll —
    each has_session is its own server round-trip.
    """
    try:
        return {str(session.name) for session in _tmux_server.sessions}
    except LibTmuxException:
        return set()


def session_is_live(session: str) -> bool:
    try:
        return _tmux_server.has_session(session)
    except LibTmuxException:
        return False


def project_git_label(project: dict[str, Any]) -> str:
    """One compact, colored token for a single project entry: dim bare name
    if it isn't a git repo, light-cyan `⎇ branch` if it is, amber
    `⎇+ branch (worktree)` if it's a *linked* worktree rather than the
    repo's main checkout.

    `.git` as a directory vs. a file is the cheap, subprocess-free way to
    tell those two apart (a linked worktree's `.git` is a one-line file
    pointing at the real gitdir elsewhere — see `git worktree add`/
    `scripts/repository/git_worktrees.py`, which orcan already manages
    worktrees through). Distinguishing it matters operationally: a worktree
    shares history with its parent clone and can't be casually deleted or
    moved on its own the way a plain clone can — which is also why it gets
    amber (attention), not the same muted tone as a plain folder. All
    three colors are pre-existing cockpit roles, not new: `#67e8f9` is the
    documented "path / secondary highlight" accent (docs/*/guides/
    terminal-ui.md's palette table), `#fbbf24` is the same amber the rail's
    pending-count badge uses, `#64748b` is the standard muted tone. Flagged
    in review: everything on this line used to be one flat muted color and
    was hard to tell apart from the panel background.
    """
    name = str(project.get("name") or project.get("alias") or "?").strip() or "?"
    path = str(project.get("path") or "").strip()
    if not path:
        return f"[#64748b]{name}[/]"
    git_path = Path(path) / ".git"
    if git_path.is_file():
        branch = git_branch(path)
        label = f"⎇+ {branch} (worktree)" if branch else f"{name} (worktree)"
        return f"[#fbbf24]{label}[/]"
    if git_path.is_dir():
        branch = git_branch(path)
        label = f"⎇ {branch}" if branch else name
        return f"[#67e8f9]{label}[/]"
    return f"[#64748b]{name}[/]"


def format_workspace_row_text(
    row: dict[str, Any],
    *,
    active_session: str | None,
    expanded: bool,
) -> str:
    """Markup for one ListView row — shared by paint + signature so a no-op
    refresh can skip tear-down when the visible text would be identical."""
    dot = "●" if row["live"] else "○"
    is_active = row["session"] == active_session
    marker = "▸" if is_active else " "
    text = f"{marker}{dot} {row['name']}"
    if not expanded:
        return text
    repos = f"{row['repo_count']} repo" + ("" if row["repo_count"] == 1 else "s")
    # git status per project only for the expanded row being rendered —
    # see the "projects" comment in list_workspace_rows().
    labels = [project_git_label(p) for p in row["projects"] if isinstance(p, dict)]
    if labels:
        repos += f": {', '.join(labels)}"
    home = os.path.expanduser("~")
    root = row["root"]
    if home and root.startswith(home):
        root = "~" + root[len(home) :]
    # #94a3b8 (lighter muted), not #64748b — whole path/line in the darker
    # tone read as washed-out against this card's background.
    text += f"\n   [#94a3b8]{root}[/]"
    text += f"\n   [#94a3b8]{repos}[/]"
    return text


def workspace_list_structure(rows: list[dict[str, Any]]) -> tuple[str, ...]:
    """Stable identity of list membership/order (not ●/○ or ▸)."""
    return tuple(str(row.get("session") or "") for row in rows)


def workspace_list_paint_signature(
    rows: list[dict[str, Any]],
    *,
    active_session: str | None,
    expanded: bool,
) -> tuple[tuple[str, bool], ...]:
    """What the ListView would show — poll stays frequent; paint skips when
    this matches the last painted signature (avoids clear()+rebuild flicker)."""
    return tuple(
        (
            format_workspace_row_text(
                row, active_session=active_session, expanded=expanded
            ),
            row["session"] == active_session,
        )
        for row in rows
    )


def list_workspace_rows(config_path: str | None = None) -> list[dict[str, Any]]:
    cfg = load_config(config_path)
    live = live_session_names()
    rows: list[dict[str, Any]] = []
    for ws in iter_workspaces(cfg):
        rows.append(
            {
                "name": ws["name"],
                "root": ws["root"],
                "session": ws["tmux_session"],
                "hints": compact_hints(ws),
                "live": ws["tmux_session"] in live,
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


def workspace_roots(config_path: str | None = None) -> list[Path]:
    """Enabled workspace roots from config only — no tmux live probes.

    Used when callers only need paths (e.g. cross-workspace pending counts),
    so a watchfiles burst does not pay N× ``has_session`` via
    ``list_workspace_rows``.
    """
    cfg = load_config(config_path)
    return [Path(ws["root"]) for ws in iter_workspaces(cfg) if ws.get("root")]


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
        # Last painted ListView / glance — poll stays on the timer; paint
        # skips when signatures match so idle refresh does not flicker.
        self._list_paint_sig: tuple[tuple[str, bool], ...] | None = None
        self._list_structure: tuple[str, ...] | None = None
        self._glance_text: str | None = None

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
        paint_sig = workspace_list_paint_signature(
            self.rows,
            active_session=self.active_session,
            expanded=self._expanded,
        )
        if paint_sig == self._list_paint_sig:
            return
        list_view = self.query_one("#workspace-list", ListView)
        structure = workspace_list_structure(self.rows)
        items = list(list_view.query(ListItem))
        # Same membership/order → mutate labels in place (●/○ / ▸ / expand)
        # instead of clear()+append, which flashes even for one-cell edits.
        if (
            structure == self._list_structure
            and len(items) == len(self.rows)
            and self._list_structure is not None
        ):
            for item, (text, is_active) in zip(items, paint_sig):
                item.query_one(Label).update(text)
                item.set_class(is_active, "active-workspace")
        else:
            selected = list_view.index
            list_view.clear()
            for (text, is_active), row in zip(paint_sig, self.rows):
                item = ListItem(Label(text))
                if is_active:
                    item.add_class("active-workspace")
                list_view.append(item)
            if selected is not None and selected < len(self.rows):
                list_view.index = selected
        self._list_paint_sig = paint_sig
        self._list_structure = structure

    def _highlighted_row(self) -> dict[str, Any] | None:
        list_view = self.query_one("#workspace-list", ListView)
        index = list_view.index
        if index is None or not (0 <= index < len(self.rows)):
            return None
        return self.rows[index]

    def _update_glance(self) -> None:
        row = self._highlighted_row()
        if row is None:
            text = format_glance([], empty_hint=_GLANCE_EMPTY)
        else:
            lines = glance_lines(
                row["session"],
                row["root"],
                live=bool(row["live"]),
                projects=row.get("projects"),
            )
            text = format_glance(lines, empty_hint=_GLANCE_EMPTY)
        if text == self._glance_text:
            return
        self._glance_text = text
        self.query_one("#workspace-glance", Static).update(text)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        self._update_glance()

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        index = event.list_view.index
        if index is None or not (0 <= index < len(self.rows)):
            return
        await self.app.select_workspace(self.rows[index])  # type: ignore[attr-defined]

    def action_quit_app(self) -> None:
        self.app.exit()
