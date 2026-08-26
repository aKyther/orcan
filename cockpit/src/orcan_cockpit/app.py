"""Textual cockpit app: a single, persistent layout — top bar (utility rail
+ CPU/RAM/clock) · workspaces + ASSERTIONS activity (left column) ·
embedded live tmux session + contextual hint strip (center) · status bar
(bottom, workspace identity).
This is what cli.py launches on a real tty.

tmux stays the real session/window/pane engine throughout: the center
column only owns the outer pty (PtyTerminal spawns `tmux attach` as its
child) and the rest of this app renders around it. Nothing here
re-implements tmux's own session/window/pane logic — context review is
launched as a real tool via `tmux display-popup` (actions.py), not
reimplemented as a widget. (A matching Git/lazygit popup shortcut used to
live in the rail/F3 — removed on request as redundant with the `lg` shell
alias already available inside the terminal.)
"""

from __future__ import annotations

from typing import Iterable

from textual import events
from textual.app import App, ComposeResult, SystemCommand
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import ListView, Static

from orcan_cockpit.about_modal import AboutModal
from orcan_cockpit.activity import WorkspaceActivity
from orcan_cockpit.actions import (
    run_context_review_popup,
    toggle_automation_enabled,
    toggle_automation_pause,
)
from orcan_cockpit.commands import WorkspaceCommands
from orcan_cockpit.hints import HintStrip
from orcan_cockpit.picker import WorkspaceList, bootstrap_workspace
from orcan_cockpit.pty_terminal import PtyTerminal
from orcan_cockpit.rail import UtilityRail
from orcan_cockpit.shortcuts import Context
from orcan_cockpit.shortcuts_modal import ShortcutsModal
from orcan_cockpit.status import Tier, tier_for_width
from orcan_cockpit.status_bar import StatusBar
from orcan_cockpit.top_bar import TopBar

PLACEHOLDER_TEXT = (
    "[#a78bfa bold]🌀 orcan[/]\n"
    "Pick a workspace on the left · Enter to attach\n"
    "[#64748b]F1 shortcuts · F4 panels · F2 assertions[/]"
)

# Maps a focused widget's own id (walked up via .parent — covers any nested
# descendant, e.g. the ListView inside WorkspaceList) to the hint-strip
# context it represents. "panel" now means "the ASSERTIONS section at the
# bottom of the left column" (activity.py's WorkspaceActivity) rather than a
# separate right-hand panel — the Context literal name is kept as "panel" so
# shortcuts.py's existing manifest entries (r, p, etc.) don't need renaming.
_CONTEXT_ROOT_IDS: dict[str, Context] = {
    "terminal": "terminal",
    "workspace-list-widget": "workspaces",
    "workspace-activity": "panel",
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


# Each of the three main panels (workspace list, assertions, terminal) is
# its own bordered card — cyan on focus, matching tmux's own
# pane-active-border-style (status.conf). "terminal" maps to #center-stack
# (the card wraps the terminal/placeholder/loading stack, not the hint
# strip below it) — giving the terminal a border/padding was an explicit,
# deliberate tradeoff (costs a couple of real tmux columns/rows) confirmed
# with the user rather than assumed. No "rail" entry: it's a row of
# individually-focusable buttons in the top bar now, not a bordered column —
# each button already gets its own :hover/:focus color (rail.py's CSS), so a
# whole-row border highlight would be redundant.
_FOCUS_BORDER_IDS: dict[Context, str] = {
    "workspaces": "#workspace-list-widget",
    "panel": "#workspace-activity",
    "terminal": "#center-stack",
}


# Same navy/cyan palette as the rest of orcan's terminal UI (tmux status
# bar, ttyd theme — see docker/rootfs/etc/tmux/status.conf and
# docker/rootfs/usr/local/bin/cursor-ttyd) so the cockpit reads as the same
# product, not a bolted-on framework default.
_CSS = """
Screen {
    background: #0a0e17;
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
    height: 3;
    background: #0d1520;
    border: round #334155;
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
    color: #a78bfa;
    text-style: bold;
}

#top-bar-identity:hover {
    background: #1e293b;
}

#rail {
    layout: horizontal;
    width: auto;
    background: #0d1520;
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
    background: #0d1520;
    color: #64748b;
    border: none;
}

#rail Button:hover, #rail Button:focus {
    color: #5eead4;
    background: #1e293b;
}

/* Pending assertions pulse (UtilityRail._pulse_tick) — amber blink so the
   bell is noticeable without a second status surface. */
#rail-assertions.pending-pulse {
    color: #fbbf24;
    background: #1e293b;
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
    color: #94a3b8;
}

#main-row {
    height: 1fr;
}

#workspaces {
    width: 34;
    background: #0a0e17;
}

#workspace-list-widget {
    /* No margin-bottom (previously 1): the blank row it left between this
       card and ASSERTIONS below read as unused space, not intentional
       breathing room (flagged in review). Removing it hands that row back
       to this card's own height:1fr — one more visible row in the actual
       workspace list — instead of sitting empty as a gap. */
    layout: vertical;
    height: 1fr;
    background: #0d1520;
    border: round #334155;
    padding: 0 1;
}

#workspace-list-widget.focused {
    border: round #5eead4;
}

#workspaces ListView {
    height: 1fr;
    background: transparent;
}

#workspace-glance {
    /* Session glance under the highlighted workspace — 2–3 lines of
       pending / reflection / pane commands (session_glance.py). */
    height: auto;
    max-height: 4;
    color: #94a3b8;
    padding-top: 1;
}

#workspace-legend {
    /* height:2, not 1: the full legend text (44 cells) is wider than this
       card's ~30-col usable width and was silently clipping "[i] expand"
       off the end entirely — found while verifying the `i` expand feature
       actually renders. Two lines fit both without truncation. */
    height: 2;
    color: #64748b;
}

/* The currently-ATTACHED workspace (not just the keyboard cursor's current
   row) — a light, permanent highlight distinct from ListView's own
   built-in cursor-row style, which only shows while this list has focus. */
#workspace-list ListItem.active-workspace {
    background: #1e293b;
}

#workspace-activity {
    height: auto;
    max-height: 60%;
    background: #0d1520;
    border: round #334155;
    padding: 0 1;
    color: #64748b;
    overflow-y: auto;
}

#workspace-activity.focused {
    border: round #5eead4;
}

.activity-heading {
    /* Violet — same "static landmark, not focus state" role as
       #top-bar-identity above. */
    color: #a78bfa;
    text-style: bold;
}

#activity-subtitle {
    color: #64748b;
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
    background: #1e293b;
    /* Violet — same "static landmark" role as .activity-heading; cyan
       stays reserved for the card's own .focused border. */
    color: #a78bfa;
    content-align: center middle;
}

#activity-actions Button:hover {
    background: #334155;
}

#activity-actions Button:disabled {
    color: #475569;
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
       border position). #center's outer padding was making #center-stack/
       #hint-strip render narrower than #top-bar's true full-width span
       above them and #workspaces' cards beside them — exactly the
       misalignment being fixed here. */
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
    background: #0d1520;
    border: round #334155;
    padding: 1;
}

#center-stack.focused {
    border: round #5eead4;
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
    color: #64748b;
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
    color: #c8d3e0;
    background: #0a0e17;
}

#hint-strip {
    /* Bordered card, matching top-bar/side-panels/terminal (border-top +
       content + border-bottom; see #top-bar's comment for the box-model
       gotcha this avoids). height:auto (was a fixed 3) with a min/max
       band: the hint text already wraps correctly inside #hint-body at
       narrow widths (confirmed via Textual's own layout — content wants
       up to 4 rows at 100 cols), but a fixed height:3 silently clipped
       every row past the first, which read as "no wrapping" (flagged in
       review) when it was actually wrapping into space that didn't exist.
       max-height keeps a very narrow terminal from letting this strip eat
       too much of the screen — content still simply clips past that,
       same as before, just only in a genuinely extreme case now instead
       of always. No margin-top (previously 1): this strip is a caption FOR
       the terminal above it (contextual hints for whatever has focus), not
       a separate section — flagged as an unexplained gap in review (the
       left column's own inter-card gap got the same "unused space" call
       and was removed too — see #workspace-list-widget). width: 1fr is
       NOT a default — without it this card sizes to fit its own text
       content instead of stretching to match #center-stack's width above
       it, which is exactly why they looked misaligned/uneven. */
    width: 1fr;
    height: auto;
    min-height: 3;
    max-height: 6;
    background: #0d1520;
    border: round #334155;
    color: #94a3b8;
    padding: 0 1;
}

#status-bar {
    /* Bordered card, matching #top-bar (the other full-width bookend) —
       same height:3 reasoning as #top-bar's comment. */
    height: 3;
    background: #0d1520;
    border: round #334155;
    color: #94a3b8;
    padding: 0 1;
}

#sidebar-toggle {
    /* Persistent edge-of-panel toggle (chevron) — lives outside
       #workspaces so it's still visible/clickable when that column is
       hidden (F4 or this arrow both drive the same
       _update_workspaces_visibility, which also keeps this arrow's label
       in sync — one state, two controls, matching the rest of this file's
       "one source of truth, multiple renderers" pattern). Replaces the
       rail's old hamburger button (removed from rail.py) — this is the
       more standard IDE affordance for a collapsible sidebar.

       A plain Static, not a Button: Button's own DEFAULT_CSS carries a
       "tall" border and padding that fought this widget's width:1 and
       corrupted that entire terminal row's compositing (confirmed via
       real pty+pyte rendering — see AGENTS.md's box-model gotcha note for
       why this class of bug needs that verification, not just headless).
       Static has no such baggage. background matches the card borders'
       own color (#334155) rather than the screen background, so this
       1-column strip reads as a thickened, clickable continuation of the
       card's edge rather than a separate gap next to it. */
    width: 1;
    height: 1fr;
    background: #334155;
    color: #0a0e17;
    text-style: bold;
    content-align: center middle;
}

#sidebar-toggle:hover {
    background: #5eead4;
}

/* Terminal-column tiers (MainScreen.on_resize) — not browser breakpoints.
   #workspaces is NOT listed here even though it hides at the minimal tier:
   it also has a manual F4/hamburger toggle (_workspaces_visible), and
   Python's widget.display assignment and a stylesheet display:none class
   both drive the same underlying style — mixing them is exactly the kind
   of two-sources-of-truth bug that's easy to get wrong. MainScreen
   computes #workspaces' effective visibility itself (tier AND manual
   toggle combined — see _update_workspaces_visibility) instead. #top-bar
   has no manual toggle, so a plain CSS rule is fine for it — hidden at the
   minimal tier along with everything else to maximize terminal space; its
   F1-F4 bindings keep working even while it's invisible. */
MainScreen.tier-minimal #top-bar {
    display: none;
}
"""


class MainScreen(Screen):
    """The one persistent screen: top bar (utility rail + CPU/RAM/clock),
    left workspace list + ASSERTIONS activity, center terminal + hints,
    bottom status bar — all mounted together, never torn down and
    rebuilt."""

    BINDINGS = [
        ("f2", "toggle_panel", "Toggle panel"),
        # Bare function keys — not letters/Ctrl/Alt — because PtyTerminal
        # swallows (event.stop()) any key it can translate to pty bytes
        # whenever the terminal has focus (see pty_terminal.py's on_key);
        # only bare F-keys reliably reach these bindings regardless of
        # which widget currently has focus.
        ("f1", "open_shortcuts", "Shortcuts"),
        ("question_mark", "open_shortcuts", "Shortcuts"),
        ("f4", "toggle_workspaces", "Toggle workspaces"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._panel_visible = True
        self._workspaces_visible = True
        self._current_session: str | None = None
        self._tier: Tier = "full"

    def compose(self) -> ComposeResult:
        yield TopBar(id="top-bar")
        with Horizontal(id="main-row"):
            with Vertical(id="workspaces"):
                yield WorkspaceList(id="workspace-list-widget")
                yield WorkspaceActivity(id="workspace-activity")
            yield Static("‹", id="sidebar-toggle")
            with Container(id="center"):
                with Container(id="center-stack"):
                    yield Static(PLACEHOLDER_TEXT, id="placeholder")
                yield HintStrip(id="hint-strip")
        yield StatusBar(id="status-bar")

    def on_click(self, event: events.Click) -> None:
        if event.widget is not None and event.widget.id == "sidebar-toggle":
            event.stop()
            self.action_toggle_workspaces()
        elif event.widget is not None and event.widget.id == "top-bar-identity":
            # The wordmark as a dedicated About entry point — separate from
            # F1/"? Help" (shortcuts), not a second way to reach the same
            # thing: "what is this app" and "what are the keybindings" are
            # different questions (flagged in review — About used to be
            # bundled into the shortcuts modal). No second bell here
            # anymore either — see status.py: the bottom bar's own 🔔 was a
            # duplicate of the rail's and got dropped, not kept as a second
            # click target.
            event.stop()
            self.app.push_screen(AboutModal())

    def on_mount(self) -> None:
        # Nothing's attached yet — start with the workspace list focused so
        # arrow keys + Enter work immediately, no Tab hunting required.
        self.query_one("#workspace-list-widget", WorkspaceList).query_one(ListView).focus()
        self.query_one(HintStrip).set_target("workspaces")
        self._update_focus_highlight("workspaces")
        self._apply_tier(tier_for_width(self.size.width))
        self.query_one("#sidebar-toggle", Static).tooltip = "Toggle workspace panel (F4)"

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
        # Combines the tier-driven auto-collapse with the manual F4/edge-
        # arrow toggle — see the CSS comment above _CSS's tier rules for why
        # this can't just be a stylesheet class rule like #rail's. Single
        # place both #workspaces' actual visibility AND the arrow's label
        # get set from, so they can never disagree.
        visible = self._workspaces_visible and self._tier != "minimal"
        self.query_one("#workspaces").display = visible
        self.query_one("#sidebar-toggle", Static).update("‹" if visible else "›")

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        context = _classify_focus(event.widget)
        if context is not None:
            self.query_one(HintStrip).set_target(context)
            self._update_focus_highlight(context)

    def _update_focus_highlight(self, context: Context) -> None:
        # Iterate unique selectors, not (context, selector) pairs: "workspaces"
        # and "panel" now share the same #workspaces selector, so naively
        # setting/clearing per-context would have the later dict entry
        # clobber the earlier one's result for the same widget.
        target_selector = _FOCUS_BORDER_IDS.get(context)
        for selector in set(_FOCUS_BORDER_IDS.values()):
            self.query_one(selector).set_class(selector == target_selector, "focused")

    def select_workspace(self, row: dict) -> None:
        if row["session"] == self._current_session:
            return  # already attached here — no need to tear down and respawn

        center = self.query_one("#center-stack", Container)
        center.remove_children()
        center.mount(
            Static(
                f"[#a78bfa bold]🌀[/] attaching [#5eead4]{row['name']}[/]\n"
                f"[#64748b]tmux:{row['session']}[/]",
                id="loading",
            )
        )

        bootstrap = bootstrap_workspace(row)
        if bootstrap.returncode != 0:
            self._current_session = None
            center.remove_children()
            center.mount(Static(f"Could not bootstrap session {row['session']!r}", id="error"))
            return

        self._current_session = row["session"]
        # Keep the attaching card until PtyTerminal.Ready — avoids a blank
        # flash between bootstrap and the first PTY paint.
        center.mount(
            PtyTerminal(
                ["tmux", "attach", "-t", f"={row['session']}"],
                session=row["session"],
                id="terminal",
            )
        )
        self.query_one("#workspace-list-widget", WorkspaceList).set_active_session(row["session"])
        self.query_one(WorkspaceActivity).set_workspace(row["root"], row["session"])
        self.query_one(StatusBar).set_workspace(row["name"], row["root"], row["session"])

    def on_pty_terminal_ready(self, message: PtyTerminal.Ready) -> None:
        loading = self.query("#loading")
        if loading:
            loading.remove()
        message.pty_terminal.focus()

    def action_toggle_panel(self) -> None:
        activity = self.query_one(WorkspaceActivity)
        self._panel_visible = not self._panel_visible
        activity.display = self._panel_visible
        if self._panel_visible:
            activity.focus()
        else:
            terminal = self.query("#terminal")
            if terminal:
                terminal.focus()

    def action_toggle_workspaces(self) -> None:
        self._workspaces_visible = not self._workspaces_visible
        self._update_workspaces_visibility()
        if self._workspaces_visible and self._tier != "minimal":
            self.query_one("#workspace-list-widget", WorkspaceList).query_one(ListView).focus()
        else:
            terminal = self.query("#terminal")
            if terminal:
                terminal.focus()

    def action_open_shortcuts(self) -> None:
        self.app.push_screen(ShortcutsModal())

    def _reveal_assertions(self) -> None:
        # Assertions live inside #workspaces now — clicking either bell (the
        # rail's, or the status bar's — see on_click) should always get you
        # there, so un-hide the whole left column too if F4 had hidden it,
        # not just the assertions sub-section. Single method so the two
        # click sources can't drift into different behavior.
        if not self._workspaces_visible:
            self._workspaces_visible = True
            self._update_workspaces_visibility()
        activity = self.query_one(WorkspaceActivity)
        if not self._panel_visible:
            self._panel_visible = True
            activity.display = True
        activity.focus()

    def on_utility_rail_tool_selected(self, message: UtilityRail.ToolSelected) -> None:
        if message.tool == "assertions":
            self._reveal_assertions()
        elif message.tool == "shortcuts":
            self.action_open_shortcuts()

    def on_workspace_activity_summary_updated(self, message: WorkspaceActivity.SummaryUpdated) -> None:
        self.query_one(UtilityRail).set_pending_count(message.count)


class CockpitApp(App):
    """ttyd's PTY command when a real tty is attached — see cli.py."""

    TITLE = "orcan"
    CSS = _CSS
    COMMANDS = App.COMMANDS | {WorkspaceCommands}

    def on_mount(self) -> None:
        self.push_screen(MainScreen())

    def select_workspace(self, row: dict) -> None:
        main = self.screen
        assert isinstance(main, MainScreen)
        main.select_workspace(row)

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        yield from super().get_system_commands(screen)
        if not isinstance(screen, MainScreen):
            return
        yield SystemCommand("Toggle assertions panel", "F2", screen.action_toggle_panel)
        yield SystemCommand("Toggle workspaces panel", "F4", screen.action_toggle_workspaces)
        yield SystemCommand("Open shortcuts", "F1 / ?", screen.action_open_shortcuts)
        if screen._current_session:
            session = screen._current_session
            yield SystemCommand(
                "Run context review", "r (panel focused)", lambda: run_context_review_popup(session)
            )
            def _toggle_pause() -> None:
                toggle_automation_pause()
                screen.query_one(WorkspaceActivity).refresh_summary()

            def _toggle_enabled() -> None:
                toggle_automation_enabled()
                screen.query_one(WorkspaceActivity).refresh_summary()

            yield SystemCommand(
                "Pause/resume context automation",
                "p (panel focused)",
                _toggle_pause,
            )
            yield SystemCommand(
                "Turn context automation off/on",
                "o (panel focused)",
                _toggle_enabled,
            )


def run_cockpit() -> int:
    CockpitApp().run()
    return 0
