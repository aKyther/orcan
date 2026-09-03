"""Textual cockpit app: a single, persistent layout — top bar (utility rail
+ CPU/RAM/clock) · workspace picker (overlay) · embedded live tmux session
(center) · status bar (bottom, workspace identity).
This is what cli.py launches on a real tty.

tmux stays the real session/window/pane engine throughout: the center
column only owns the outer pty (PtyTerminal spawns `tmux attach` as its
child) and the rest of this app renders around it. Nothing here
re-implements tmux's own session/window/pane logic. Git remains available
through the `lg` shell alias inside the terminal.
"""

from __future__ import annotations

from typing import Iterable

from textual import events
from textual.app import App, ComposeResult, SystemCommand
from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import ListView, Static

from orcan_cockpit.about_modal import AboutModal
from orcan_cockpit.commands import WorkspaceCommands
from orcan_cockpit.first_run import FirstRunModal
from orcan_cockpit.onboarding import onboarding_already_seen
from orcan_cockpit.peek_modal import PeekModal
from orcan_cockpit.picker import WorkspaceList, bootstrap_workspace
from orcan_cockpit.pty_terminal import PtyTerminal
from orcan_cockpit.rail import UtilityRail
from orcan_cockpit.shortcuts import Context
from orcan_cockpit.shortcuts_modal import ShortcutsModal
from orcan_cockpit.status import Tier, tier_for_width
from orcan_cockpit.status_bar import StatusBar
from orcan_cockpit.state import read_last_session, remember_session
from orcan_cockpit.tmux_chrome import (
    TASK_TEMPLATES,
    focus_pinned_pane,
    pin_main_pane,
    run_url_picker,
    split_run,
)
from orcan_cockpit.top_bar import TopBar

PLACEHOLDER_TEXT = (
    "[#c7b1e2 bold]🌀 orcan[/]\n"
    "Choose a workspace\n"
    "[#948ba3]Your sessions and projects will appear here.[/]"
)

# Maps a focused widget to the context that drives its focus-highlight border.
_CONTEXT_ROOT_IDS: dict[str, Context] = {
    "terminal": "terminal",
    "workspace-list-widget": "workspaces",
    "rail": "rail",
}


def _classify_focus(widget) -> Context | None:
    node = widget
    while node is not None:
        context = _CONTEXT_ROOT_IDS.get(node.id or "")
        if context is not None:
            return context
        node = node.parent
    return None


# The workspace list and terminal each get their own bordered card — cyan on
# focus, matching tmux's own pane-active-border-style (status.conf).
# "terminal" maps to #center-stack (the card wraps the
# terminal/placeholder/loading stack) — giving the terminal a border/padding
# was an explicit, deliberate tradeoff (costs a couple of real tmux
# columns/rows) confirmed with the user rather than assumed. No "rail" entry:
# it's a row of
# individually-focusable buttons in the top bar now, not a bordered column —
# each button already gets its own :hover/:focus color (rail.py's CSS), so a
# whole-row border highlight would be redundant.
_FOCUS_BORDER_IDS: dict[Context, str] = {
    "workspaces": "#workspace-list-widget",
    "terminal": "#center-stack",
}


# Warm, twilight-plum colours shared by Cockpit and terminal chrome, so the
# interface remains one product while feeling less austere than near-black.
_CSS = """
Screen {
    background: #12101a;
}

#top-bar {
    /* A real bordered card, matching the side panels/terminal — height:3
       is deliberate, not a guess: border-top(1) + content(1) + border-
       bottom(1), the minimum a bordered box needs. height:1 + a border
       here would eat the ENTIRE row for the border line alone and hide
       the content again — see the box-model note under "Pay attention to"
       in AGENTS.md/CLAUDE.md, a real bug this session's headless tests
       didn't catch (they only assert stored widget state, not actual
       glyph-level terminal compositing — verify any change here against
       real pty+pyte output, not just headless Pilot). padding is
       horizontal-only (0 1), same as the other cards, so it doesn't need
       extra rows beyond the border itself. #rail/#top-bar-right below
       deliberately carry NO horizontal padding of their own — it would
       stack on top of this padding, the same double-padding bug already
       fixed once for the side panels this session. */
    layout: horizontal;
    height: 2;
    background: #1b1724;
    padding: 0 1;
}

#top-bar-identity {
    /* Cheap, static brand anchor at the very left edge of the top bar —
       today the bar opens straight into bare icon buttons with nothing to
       orient on. The active workspace name is already shown in the bottom
       status bar (StatusBar.set_workspace) so it isn't repeated here; a
       fixed wordmark avoids wiring a second, redundant data path for the
       same fact. Also doubles as the About entry point (click — see
       MainScreen.on_click, about_modal.py) since "click the app name" is
       a common enough convention to be worth the free real estate. */
    width: auto;
    height: 1;
    margin-right: 2;
    /* Violet, not cyan: cyan is reserved for keyboard-focus state
       exclusively now (see the .focused rules below) — reusing it here
       too was flagged in review as "everything is the same color".
       Violet already exists in the product's own ANSI palette
       (cursor-ttyd's theme JSON, magenta), reused rather than inventing
       a new hex. */
    color: #c7b1e2;
}

#top-bar-identity:hover {
    color: #e2ddea;
}

#workspace-trigger {
    width: auto;
    height: 1;
    margin-right: 2;
    padding: 0 1;
    color: #cbc4d3;
    background: #2a2237;
}

#workspace-trigger:hover, #workspace-trigger.picker-open {
    color: #d7c7eb;
    background: #342a44;
}

#rail {
    layout: horizontal;
    width: auto;
    background: #1b1724;
}

#rail Button {
    /* width:auto (not a fixed 3) because the label text itself now varies:
       icon-only at compact/minimal tiers, "icon + word" at the full tier
       (UtilityRail.set_tier) — a fixed width would either clip the wide
       label or leave a gap around the narrow one. */
    width: auto;
    min-width: 3;
    height: 1;
    margin-right: 1;
    padding: 0 1;
    background: #1b1724;
    color: #948ba3;
    border: none;
}

#rail Button:hover, #rail Button:focus {
    color: #d7c7eb;
    background: #2a2237;
}


#top-bar-spacer {
    width: 1fr;
    height: 1;
}

#top-bar-right {
    /* A fixed width (set from Python in top_bar.py's refresh_metrics, via
       rich.cells.cell_len — not a CSS width:auto or width:1fr), and left
       align (default). Two real Rich/Textual rendering bugs found by
       testing, both duplicating the string's last character at the
       boundary: (1) content-align:right combined with width:1fr, and (2)
       width:auto with content that changes across refresh_metrics() ticks
       (its auto-computed box size appears to lag one render behind). An
       exact Python-computed width sidesteps both while still hugging the
       text tightly — no leftover gap before the card's right edge like a
       static oversized guess left. #top-bar-spacer above does the "push to
       the right edge" job via layout, not text alignment. */
    height: 1;
    color: #948ba3;
}

#main-row {
    layers: base overlay;
    height: 1fr;
}

#workspaces {
    layer: overlay;
    dock: left;
    width: 52;
    height: 80%;
    margin-left: 1;
    background: #211c2b;
}

#workspace-list-widget {
    /* No margin-bottom (previously 1): the blank row it left between this
       card reads as unused space, not intentional
       breathing room (flagged in review). Removing it hands that row back
       to this card's own height:1fr — one more visible row in the actual
       workspace list — instead of sitting empty as a gap. */
    layout: vertical;
    height: 1fr;
    background: #211c2b;
    border-left: solid #604e72;
    padding: 0 1;
}

#workspace-list-widget.focused {
    border-left: solid #ad91d0;
}

#workspaces ListView {
    height: 1fr;
    background: transparent;
}

#workspace-glance {
    /* Session glance under the highlighted workspace — 2–3 lines of
       brief / pane commands (session_glance.py). */
    height: auto;
    max-height: 4;
    color: #b0a6ba;
    padding-top: 1;
}

#workspace-details {
    height: auto;
    max-height: 8;
    color: #b0a6ba;
    padding-top: 1;
}

#workspace-legend {
    /* height:2, not 1: the full legend text (44 cells) is wider than this
       card's ~30-col usable width and was silently clipping "[i] expand"
       off the end entirely — found while verifying the `i` expand feature
       actually renders. Two lines fit both without truncation. */
    height: 2;
    color: #948ba3;
}

/* The currently-ATTACHED workspace (not just the keyboard cursor's current
   row) — a light, permanent highlight distinct from ListView's own
   built-in cursor-row style, which only shows while this list has focus. */
#workspace-list ListItem.active-workspace {
    background: #302640;
}

#workspace-activity {
    height: auto;
    max-height: 60%;
    background: #211c2b;
    border-left: solid #604e72;
    padding: 0 1;
    color: #948ba3;
    overflow-y: auto;
}

#workspace-activity.focused {
    border-left: solid #ad91d0;
}

.activity-heading {
    /* Violet — same "static landmark, not focus state" role as
       #top-bar-identity above. */
    color: #c7b1e2;
    text-style: bold;
}

#activity-subtitle {
    color: #948ba3;
    margin-bottom: 1;
}

#activity-actions {
    layout: horizontal;
    height: 1;
    margin-bottom: 1;
}

#activity-actions Button {
    /* Textual's Button DEFAULT_CSS carries `border: tall` (renders as
       thick-looking half-block rows above/below the label — confirmed in
       this session's own pty dumps) plus `min-width: 16`. Both are
       overridden here: border:none drops the bulky look (this is what made
       the old full-width "Review" button look "giant"), and min-width:0
       lets width:1fr actually split the row three ways instead of each
       button demanding 16 columns regardless of the card's real width. */
    width: 1fr;
    min-width: 0;
    height: 1;
    border: none;
    background: #2a2237;
    /* Violet — same "static landmark" role as .activity-heading; cyan
       stays reserved for the card's own .focused border. */
    color: #c7b1e2;
    content-align: center middle;
}

#activity-actions Button:hover {
    background: #342a44;
}

#activity-actions Button:disabled {
    color: #746a82;
}

#activity-pause-btn,
#activity-enabled-btn {
    margin-left: 1;
}

#center {
    /* No padding here (previously 0 1) — #workspaces, the analogous
       sidebar column, carries none either; its cards' own borders sit
       flush against the column edge, with padding only *inside* each card
       (#workspace-list-widget's `padding: 0 1`, for its text, not its
       border position). #center's outer padding was making #center-stack
       render narrower than #top-bar's true full-width span above it and
       #workspaces' cards beside it — exactly the misalignment being fixed
       here. */
    layout: vertical;
    width: 1fr;
    height: 1fr;
}

#center-stack {
    /* base = terminal; overlay = loading spinner shown on top of it while
       tmux attaches, removed once PtyTerminal.Ready fires — see
       MainScreen.select_workspace/on_pty_terminal_ready. Without layers,
       mounting both as plain siblings would stack them instead of overlay.
       The border+padding here is a deliberate tradeoff confirmed with the
       user: it costs a couple of tmux's actual columns/rows, in exchange
       for matching the bordered-card look of the side panels. */
    layers: base overlay;
    width: 1fr;
    height: 1fr;
    /* The embedded terminal already has a one-cell visual gutter on its
       right edge (scrollbar/cursor boundary). Match it on the left so the
       content does not look pasted to the viewport while retaining almost
       the full tmux width. */
    margin-left: 1;
    background: #12101a;
}

#center-stack.focused {
    background: #17131f;
}

#terminal {
    layer: base;
    width: 1fr;
    height: 1fr;
}

#placeholder, #error {
    layer: base;
    width: 1fr;
    height: 1fr;
    content-align: center middle;
    color: #948ba3;
}

#error {
    color: #f87171;
}

#loading {
    /* Overlay until PtyTerminal.Ready — branded attach card, not a spinner. */
    layer: overlay;
    width: 1fr;
    height: 1fr;
    content-align: center middle;
    color: #e2ddea;
    background: #12101a;
}

#status-bar {
    /* Bordered card, matching #top-bar (the other full-width bookend) —
       same height:3 reasoning as #top-bar's comment. */
    height: 2;
    background: #1b1724;
    color: #948ba3;
    padding: 0 1;
}

/* Terminal-column tiers (MainScreen.on_resize) — not browser breakpoints.
   #workspaces is NOT listed here because it has a manual F4/pill toggle, and
   Python's widget.display assignment and a stylesheet display:none class
   both drive the same underlying style — mixing them is exactly the kind
   of two-sources-of-truth bug that's easy to get wrong. MainScreen
   computes #workspaces' effective visibility itself (tier AND manual
   toggle combined — see _update_workspaces_visibility) instead. #top-bar
   has no manual toggle, so a plain CSS rule is fine for it — hidden at the
   minimal tier along with everything else to maximize terminal space; its
   F1-F4 bindings keep working even while it's invisible. */
MainScreen.tier-minimal #rail,
MainScreen.tier-minimal #top-bar-spacer,
MainScreen.tier-minimal #top-bar-right {
    display: none;
}

MainScreen.tier-minimal #workspaces {
    width: 1fr;
}
"""


class MainScreen(Screen):
    """The one persistent screen: top bar (utility rail + CPU/RAM/clock),
    left workspace list, center terminal + hints,
    bottom status bar — all mounted together, never torn down and
    rebuilt."""

    BINDINGS = [
        # Bare function keys — not letters/Ctrl/Alt — because PtyTerminal
        # swallows (event.stop()) any key it can translate to pty bytes
        # whenever the terminal has focus (see pty_terminal.py's on_key);
        # only bare F-keys reliably reach these bindings regardless of
        # which widget currently has focus.
        ("f1", "open_shortcuts", "Shortcuts"),
        ("question_mark", "open_shortcuts", "Shortcuts"),
        ("f4", "toggle_workspaces", "Toggle workspaces"),
        ("f5", "open_peek", "Peek session brief"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._workspaces_visible = True
        self._current_session: str | None = None
        self._current_root: str | None = None
        self._tier: Tier = "full"

    def compose(self) -> ComposeResult:
        yield TopBar(id="top-bar")
        with Container(id="main-row"):
            with Vertical(id="workspaces"):
                yield WorkspaceList(id="workspace-list-widget")
            with Container(id="center"):
                with Container(id="center-stack"):
                    yield Static(PLACEHOLDER_TEXT, id="placeholder")
        yield StatusBar(id="status-bar")

    def on_click(self, event: events.Click) -> None:
        if event.widget is not None and event.widget.id == "workspace-trigger":
            event.stop()
            self.action_toggle_workspaces()
        elif event.widget is not None and event.widget.id == "top-bar-identity":
            event.stop()
            self.app.push_screen(AboutModal())
        elif self._workspaces_visible and not self._event_is_within(event, "workspaces"):
            self._set_workspaces_visible(False, focus_terminal=True)
            event.stop()
        elif event.widget is not None and event.widget.id == "center-stack":
            terminal = self.query("#terminal")
            if terminal:
                terminal.focus()
                event.stop()

    @staticmethod
    def _event_is_within(event: events.Click, widget_id: str) -> bool:
        widget = event.widget
        while widget is not None:
            if widget.id == widget_id:
                return True
            widget = widget.parent
        return False

    def on_mount(self) -> None:
        # Nothing's attached yet — start with the workspace list focused so
        # arrow keys + Enter work immediately, no Tab hunting required.
        self.query_one("#workspace-list-widget", WorkspaceList).query_one(ListView).focus()
        self._update_focus_highlight("workspaces")
        self._apply_tier(tier_for_width(self.size.width))
        # A ttyd WebSocket reconnect starts a fresh cockpit process. Restore
        # its last workspace after child widgets have mounted and populated
        # the list; tmux itself retains that session's active window/pane.
        self.call_after_refresh(self._restore_workspace)
        if not onboarding_already_seen():
            self.set_timer(0.3, self._show_first_run)

    async def _restore_workspace(self) -> None:
        session = read_last_session()
        if session is None:
            return
        workspace_list = self.query_one("#workspace-list-widget", WorkspaceList)
        for index, row in enumerate(workspace_list.rows):
            if row["session"] != session:
                continue
            workspace_list.query_one(ListView).index = index
            await self.select_workspace(row)
            return

    def _show_first_run(self) -> None:
        if not onboarding_already_seen():
            self.app.push_screen(FirstRunModal())

    def on_resize(self, event: events.Resize) -> None:
        self._apply_tier(tier_for_width(event.size.width))

    def _apply_tier(self, tier: Tier) -> None:
        if tier == self._tier and self.has_class(f"tier-{tier}"):
            return
        self._tier = tier
        for name in ("tier-full", "tier-compact", "tier-minimal"):
            self.set_class(name == f"tier-{tier}", name)
        self.query_one(StatusBar).set_tier(tier)
        self.query_one(UtilityRail).set_tier(tier)
        self._update_workspaces_visibility()

    def _update_workspaces_visibility(self) -> None:
        # The picker is always an overlay, at every tier. Its visibility can
        # therefore never resize the embedded tmux viewport.
        self.query_one("#workspaces").display = self._workspaces_visible
        self.query_one("#workspace-trigger", Static).set_class(
            self._workspaces_visible, "picker-open"
        )

    def _set_workspaces_visible(self, visible: bool, *, focus_terminal: bool = False) -> None:
        self._workspaces_visible = visible
        self._update_workspaces_visibility()
        if visible:
            self.query_one("#workspace-list-widget", WorkspaceList).query_one(ListView).focus()
        elif focus_terminal:
            terminal = self.query("#terminal")
            if terminal:
                terminal.focus()

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        context = _classify_focus(event.widget)
        if context is not None:
            self._update_focus_highlight(context)

    def _update_focus_highlight(self, context: Context) -> None:
        # Iterate unique selectors, not (context, selector) pairs: "workspaces"
        # and "panel" now share the same #workspaces selector, so naively
        # setting/clearing per-context would have the later dict entry
        # clobber the earlier one's result for the same widget.
        target_selector = _FOCUS_BORDER_IDS.get(context)
        for selector in set(_FOCUS_BORDER_IDS.values()):
            self.query_one(selector).set_class(selector == target_selector, "focused")

    async def select_workspace(self, row: dict) -> None:
        workspace_list = self.query_one("#workspace-list-widget", WorkspaceList)
        for index, candidate in enumerate(workspace_list.rows):
            if candidate["session"] == row["session"]:
                workspace_list.query_one(ListView).index = index
                break
        if row["session"] == self._current_session:
            # Enter always confirms the picker. Re-selecting the attached
            # workspace should close it and return focus to the terminal,
            # without tearing down or respawning the healthy tmux PTY.
            self._set_workspaces_visible(False, focus_terminal=True)
            return

        center = self.query_one("#center-stack", Container)
        # Must await: remove_children() only *posts* a Prune message — the
        # old child (e.g. PtyTerminal(id="terminal")) is still present in
        # center's children until that message is processed. Switching
        # workspaces again (or a fast double Enter) before this completed
        # mounted a new same-id widget alongside the not-yet-removed old
        # one, raising DuplicateIds — only reachable with >1 workspace/
        # project configured, since selecting the *same* one short-circuits
        # above (confirmed via a real duplicate-ID crash report).
        await center.remove_children()
        center.mount(
            Static(
                f"Opening [#c7b1e2]{row['name']}[/]\n"
                "[#948ba3]Restoring your session…[/]",
                id="loading",
            )
        )

        bootstrap = bootstrap_workspace(row)
        if bootstrap.returncode != 0:
            self._current_session = None
            await center.remove_children()
            center.mount(Static(f"Could not bootstrap session {row['session']!r}", id="error"))
            return

        self._current_session = row["session"]
        self._current_root = row["root"]
        remember_session(row["session"])
        # Keep the attaching card until PtyTerminal.Ready — avoids a blank
        # flash between bootstrap and the first PTY paint.
        center.mount(
            PtyTerminal(
                ["tmux", "attach", "-t", f"={row['session']}"],
                session=row["session"],
                id="terminal",
            )
        )
        workspace_list.set_active_session(row["session"])
        self.query_one(TopBar).set_workspace(row["name"])
        self.query_one(StatusBar).set_workspace(row["name"], row["root"], row["session"])
        self._set_workspaces_visible(False)

    def on_pty_terminal_ready(self, message: PtyTerminal.Ready) -> None:
        loading = self.query("#loading")
        if loading:
            loading.remove()
        message.pty_terminal.focus()

    def action_toggle_workspaces(self) -> None:
        self._set_workspaces_visible(
            not self._workspaces_visible,
            focus_terminal=self._workspaces_visible,
        )

    def action_open_shortcuts(self) -> None:
        self.app.push_screen(ShortcutsModal())

    def action_open_peek(self) -> None:
        if not self._current_root:
            self.notify("Attach a workspace first", severity="warning")
            return

        self.app.push_screen(PeekModal(self._current_root))

    def on_utility_rail_tool_selected(self, message: UtilityRail.ToolSelected) -> None:
        if message.tool == "shortcuts":
            self.action_open_shortcuts()


class CockpitApp(App):
    """ttyd's PTY command when a real tty is attached — see cli.py."""

    TITLE = "orcan"
    CSS = _CSS
    COMMANDS = App.COMMANDS | {WorkspaceCommands}

    def on_mount(self) -> None:
        self.push_screen(MainScreen())

    async def select_workspace(self, row: dict) -> None:
        main = self.screen
        assert isinstance(main, MainScreen)
        await main.select_workspace(row)

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        def _pin_main(main: MainScreen, sess: str, workspace: str) -> None:
            if pin_main_pane(sess, workspace):
                main.notify("Pinned main agent pane", severity="information")
            else:
                main.notify("Could not pin pane", severity="error")

        yield from super().get_system_commands(screen)
        if not isinstance(screen, MainScreen):
            return
        yield SystemCommand("Open workspace picker", "F4", screen.action_toggle_workspaces)
        yield SystemCommand("Open shortcuts", "F1 / ?", screen.action_open_shortcuts)
        yield SystemCommand("Peek session brief", "F5", screen.action_open_peek)
        if screen._current_session:
            session = screen._current_session
            root = screen._current_root or ""
            yield SystemCommand(
                "Split pane (vertical)",
                "tmux",
                lambda: split_run(session, "zsh", vertical=True),
            )
            yield SystemCommand(
                "Split pane (horizontal)",
                "tmux",
                lambda: split_run(session, "zsh", vertical=False),
            )
            yield SystemCommand(
                "Pick URL from panes",
                "u",
                lambda: run_url_picker(session),
            )
            yield SystemCommand(
                "Pin current pane as main agent",
                "★",
                lambda: _pin_main(screen, session, root),
            )
            yield SystemCommand(
                "Focus pinned main agent",
                "★",
                lambda: focus_pinned_pane(session, root),
            )
            for name, command in TASK_TEMPLATES.items():
                yield SystemCommand(
                    f"Task: start {name}",
                    "template",
                    lambda cmd=command: split_run(session, cmd, vertical=True),
                )



def run_cockpit() -> int:
    CockpitApp().run()
    return 0
