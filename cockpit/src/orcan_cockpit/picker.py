"""Workspace picker: pure listing/formatting helpers (no Textual import
needed to use them) plus the interactive Textual screen and the non-tty
fallback menu that both sit on top of them.

Data source is the shared `orcan.workspaces` module also used by
`orcan-workspaces` and `orcan-context-status`, so workspace discovery is not
duplicated here. The module is vendored and stdlib-only; see `cli.py` for the
image library path setup.
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
        return f"[#c4a7b7]{label}[/]"
    if git_path.is_dir():
        branch = git_branch(path)
        label = f"⎇ {branch}" if branch else name
        return f"[#aa9bc2]{label}[/]"
    return f"[#64748b]{name}[/]"


def format_workspace_row_text(
    row: dict[str, Any],
    *,
    active_session: str | None,
    expanded: bool,
) -> str:
    """Markup for one ListView row — shared by paint + signature so a no-op
    refresh can skip tear-down when the visible text would be identical."""
    is_active = row["session"] == active_session
    state = "active" if is_active else ("live" if row["live"] else "new")
    text = f"{row['name']}  [#948ba3]{state}[/]"
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
    text += f"\n   [#b0a6ba]{root}[/]"
    text += f"\n   [#b0a6ba]{repos}[/]"
    return text


def workspace_list_structure(rows: list[dict[str, Any]]) -> tuple[str, ...]:
    """Stable identity of list membership/order (not runtime state)."""
    return tuple(str(row.get("session") or "") for row in rows)


def order_workspace_rows(
    rows: list[dict[str, Any]], recent_sessions: list[str]
) -> list[dict[str, Any]]:
    """Put known recent workspace choices first, preserving all other order."""
    positions = {session: index for index, session in enumerate(recent_sessions)}
    fallback = len(positions)
    return sorted(
        rows,
        key=lambda item: positions.get(str(item.get("session") or ""), fallback),
    )


def filter_workspace_rows(
    rows: list[dict[str, Any]], query: str
) -> list[dict[str, Any]]:
    """Case-insensitive quick filter over workspace name, session, and root."""
    needle = query.strip().casefold()
    if not needle:
        return rows
    return [
        row
        for row in rows
        if needle in " ".join(
            str(row.get(field) or "") for field in ("name", "session", "root")
        ).casefold()
    ]


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
from orcan_cockpit.state import read_recent_sessions  # noqa: E402
from orcan_cockpit.tmux_chrome import open_project_pane  # noqa: E402

# Keep keyboard instructions visible rather than hiding the primary mechanic
# behind a mouse-only tooltip. `\[` escapes the literal bracket: Static uses
# Rich markup, so an unescaped `[i]` would be parsed as a tag.
LEGEND = r"recent first · ↑↓ browse · Enter attach · \[i] details"

# Kept fresh enough to notice a session someone killed elsewhere without
# feeling like a busy-poll — this is cosmetic session status, not
# anything time-sensitive.
_REFRESH_INTERVAL_S = 5.0
_GLANCE_EMPTY = "↑ Enter to attach"
_PROJECT_ACTION_LIMIT = 6


class WorkspaceList(Widget):
    """Left column: persistent workspace list — like `tmux list-sessions`,
    always visible, not a one-shot picker screen you navigate away from.
    Selecting a row tells the app to (re)attach the center terminal to it.

    The default is deliberately a calm, decision-first list. Details for only
    the highlighted row (root, projects, Git/worktree/branch identity, and
    session glance) appear on demand with `i`, so context remains available
    without competing with workspace switching."""

    can_focus = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.rows: list[dict[str, Any]] = []
        self._all_rows: list[dict[str, Any]] = []
        self.active_session: str | None = None
        self._filter_query = ""
        self._filter_armed = False
        # Details belong to the highlighted workspace, never every row. Keep
        # them opt-in: switching projects is far more common than inspecting
        # all of their metadata.
        self._expanded = False
        # Last painted ListView / glance — poll stays on the timer; paint
        # skips when signatures match so idle refresh does not flicker.
        self._list_paint_sig: tuple[tuple[str, bool], ...] | None = None
        self._list_structure: tuple[str, ...] | None = None
        self._glance_text: str | None = None
        self._project_actions: list[tuple[str, str]] = []

    def compose(self) -> ComposeResult:
        yield Static(id="workspace-filter")
        yield ListView(id="workspace-list")
        yield Static(id="workspace-details")
        for index in range(_PROJECT_ACTION_LIMIT):
            yield Static(id=f"workspace-project-{index}", classes="workspace-project")
        yield Static(format_glance([], empty_hint=_GLANCE_EMPTY), id="workspace-glance")
        yield Static(LEGEND, id="workspace-legend")

    def on_mount(self) -> None:
        self.refresh_rows()
        self.set_interval(_REFRESH_INTERVAL_S, self.refresh_rows)

    def on_key(self, event: events.Key) -> None:
        # ListView (the actual focus target — see app.py's on_mount) doesn't
        # bind "i", so this bubbles up to us unstopped.
        if event.key == "ctrl+c":
            row = self._highlighted_row()
            if row is not None:
                self.app.copy_to_clipboard(row["root"])
                self.notify("Workspace root copied", severity="information")
            event.stop()
            return
        if event.key == "i" and not self._filter_query and not self._filter_armed:
            self._expanded = not self._expanded
            self._update_details()
            self._update_glance()
            event.stop()
            return
        if event.key == "backspace" and (self._filter_query or self._filter_armed):
            if self._filter_query:
                self._set_filter(self._filter_query[:-1])
            else:
                self._filter_armed = False
                self._update_filter()
            event.stop()
            return
        # Keep the established ? help binding and i details toggle intact.
        # Any other printable key starts filtering immediately; `/` is the
        # escape hatch for filters beginning with i or ?.
        # Pilot/terminal key events may omit ``character`` even for ordinary
        # printable keys; the normalized one-cell key name is an equivalent
        # fallback and keeps physical terminals and tests on the same path.
        character = event.character or (event.key if len(event.key) == 1 else "")
        if character == "/" and not self._filter_query and not self._filter_armed:
            self._filter_armed = True
            self._update_filter()
            event.stop()
        elif character and character.isprintable() and (
            character not in {"?", "i"} or self._filter_query or self._filter_armed
        ):
            self._filter_armed = False
            self._set_filter(self._filter_query + character)
            event.stop()

    def set_active_session(self, session: str | None) -> None:
        """Called by MainScreen once a workspace is actually attached — a
        different thing from ListView's own keyboard-cursor `index`
        (which row you're currently browsing), so tracked separately."""
        self.active_session = session
        self._render_rows()
        self._update_details()
        self._update_glance()

    def row_for_session(self, session: str) -> dict[str, Any] | None:
        """Find a configured workspace even while the visible list is filtered."""
        return next(
            (row for row in self._all_rows if row["session"] == session), None
        )

    def refresh_rows(self) -> None:
        try:
            self._all_rows = order_workspace_rows(
                list_workspace_rows(), read_recent_sessions()
            )
        except (OSError, ValueError) as exc:
            self.notify(f"Error reading config: {exc}", severity="error")
            self._all_rows = []
        self.rows = filter_workspace_rows(self._all_rows, self._filter_query)
        self._render_rows()
        self._update_details()
        self._update_glance()

    def _set_filter(self, query: str) -> None:
        self._filter_query = query
        self.rows = filter_workspace_rows(self._all_rows, query)
        self._list_paint_sig = None
        self._render_rows()
        list_view = self.query_one("#workspace-list", ListView)
        list_view.index = 0 if self.rows else None
        self._update_filter()
        self._update_details()
        self._update_glance()

    def _update_filter(self) -> None:
        filter_line = self.query_one("#workspace-filter", Static)
        if not self._filter_query and not self._filter_armed:
            filter_line.display = False
            return
        if self._filter_armed:
            filter_line.update("[#c7b1e2]Filter[/] type to narrow workspaces")
            filter_line.display = True
            return
        matches = len(self.rows)
        suffix = "match" if matches == 1 else "matches"
        filter_line.update(f"[#c7b1e2]Filter[/] {self._filter_query} · {matches} {suffix}")
        filter_line.display = True

    def _render_rows(self) -> None:
        paint_sig = workspace_list_paint_signature(
            self.rows,
            active_session=self.active_session,
            expanded=False,
        )
        if paint_sig == self._list_paint_sig:
            return
        list_view = self.query_one("#workspace-list", ListView)
        structure = workspace_list_structure(self.rows)
        items = list(list_view.query(ListItem))
        # Same membership/order → mutate labels in place (state / expand)
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
        glance = self.query_one("#workspace-glance", Static)
        glance.display = self._expanded
        row = self._highlighted_row()
        if not self._expanded or row is None:
            if self._glance_text != "":
                self._glance_text = ""
                glance.update("")
            return
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
        glance.update(text)

    def _update_details(self) -> None:
        details = self.query_one("#workspace-details", Static)
        details.display = self._expanded
        row = self._highlighted_row()
        if not self._expanded or row is None:
            details.update("")
            self._update_project_actions(None)
            return
        expanded = format_workspace_row_text(
            row,
            active_session=self.active_session,
            expanded=True,
        ).splitlines()[1:]
        session_state = "running" if row["live"] else "stopped"
        details.update(
            "\n".join(expanded + [f"   [#948ba3]tmux {row['session']} · {session_state}[/]"])
        )
        self._update_project_actions(row)

    def _update_project_actions(self, row: dict[str, Any] | None) -> None:
        self._project_actions = []
        if row is not None and row["live"]:
            for project in row.get("projects") or []:
                if not isinstance(project, dict):
                    continue
                path = str(project.get("path") or "").strip()
                name = str(project.get("name") or project.get("alias") or path).strip()
                if path:
                    self._project_actions.append((name, path))
                if len(self._project_actions) >= _PROJECT_ACTION_LIMIT:
                    break
        for index in range(_PROJECT_ACTION_LIMIT):
            action = self._project_actions[index] if index < len(self._project_actions) else None
            target = self.query_one(f"#workspace-project-{index}", Static)
            if action is None:
                target.display = False
            else:
                name, path = action
                target.update(f"[#c7b1e2]Open pane[/] {name} · [#948ba3]{path}[/]")
                target.display = True

    def on_click(self, event: events.Click) -> None:
        widget_id = event.widget.id if event.widget is not None else ""
        prefix = "workspace-project-"
        if not widget_id or not widget_id.startswith(prefix):
            return
        try:
            index = int(widget_id.removeprefix(prefix))
            name, path = self._project_actions[index]
        except (IndexError, ValueError):
            return
        row = self._highlighted_row()
        if row is None or not open_project_pane(row["session"], path):
            self.notify("Could not open project pane", severity="error")
        else:
            self.notify(f"Opened pane in {name}", severity="information")
        event.stop()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        self._update_details()
        self._update_glance()

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        index = event.list_view.index
        if index is None or not (0 <= index < len(self.rows)):
            return
        await self.app.select_workspace(self.rows[index])  # type: ignore[attr-defined]

    def action_quit_app(self) -> None:
        self.app.exit()
