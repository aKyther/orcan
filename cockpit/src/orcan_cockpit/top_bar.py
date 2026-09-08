"""Top bar: utility rail (left) + a quiet clock (right).

CPU/RAM stay available in the clock tooltip rather than permanently turning
the workspace chrome into a systems dashboard.
"""

from __future__ import annotations

from rich.cells import cell_len
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from orcan_cockpit.rail import UtilityRail
from orcan_cockpit.shortcuts import product_version
from orcan_cockpit.status import now_hhmm, read_loadavg, read_mem_percent
from orcan_cockpit.tmux_chrome import session_agent_label

_REFRESH_INTERVAL_S = 3.0


class TopBar(Widget):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._painted_clock: str | None = None
        self._painted_workspace: str | None = None
        self._workspace_name: str | None = None
        self._session: str | None = None

    def compose(self) -> ComposeResult:
        # 🌀 (cyclone) not ◆ — orcan's own branding is elemental (hurricane/
        # whirlwind), and this is a plain, old (Unicode 6.0) emoji that
        # renders without needing a Nerd Font, matching the ttyd-safe-fonts
        # constraint documented in Terminal UI. Static, never updated after
        # compose, so width:auto here doesn't hit the "duplicate last char"
        # Rich/Textual bug that content changing via .update() triggers
        # elsewhere (see #top-bar-right's own comment for that one).
        yield Static(f"🌀 orcan · v{product_version()}", id="top-bar-identity")
        yield Static("Select workspace  ⌄", id="workspace-trigger")
        yield UtilityRail(id="rail")
        # An empty width:1fr spacer pushes #top-bar-right to the edge via
        # layout — NOT `content-align: right` on #top-bar-right itself.
        # That combination (content-align:right + width:1fr) has a real
        # Rich/Textual rendering bug: it intermittently duplicates the
        # string's last character right at the border. Confirmed by testing
        # content-align:left in isolation (renders perfectly) — a spacer +
        # left-aligned, auto-width text sidesteps the buggy code path
        # entirely rather than working around it.
        yield Static(id="top-bar-spacer")
        yield Static(id="top-bar-right")

    def on_mount(self) -> None:
        self.query_one("#top-bar-right", Static).tooltip = (
            "clock; system load and memory appear here on hover"
        )
        self.query_one("#top-bar-identity", Static).tooltip = (
            f"About orcan cockpit · v{product_version()}"
        )
        self.query_one("#workspace-trigger", Static).tooltip = (
            "Choose a workspace and inspect its projects (F4)"
        )
        self.set_workspace(None)
        self.refresh_clock()
        self.set_interval(_REFRESH_INTERVAL_S, self.refresh_clock)
        self.set_interval(_REFRESH_INTERVAL_S, self.refresh_workspace_indicator)

    def refresh_clock(self) -> None:
        line = now_hhmm()
        right = self.query_one("#top-bar-right", Static)
        load = read_loadavg()
        memory = read_mem_percent()
        metrics = " · ".join(
            value
            for value in (
                f"load {load}" if load else "",
                f"mem {memory}" if memory else "",
            )
            if value
        )
        right.tooltip = f"{metrics} · {line}" if metrics else line
        if line == self._painted_clock:
            return
        self._painted_clock = line
        # width:auto also has a real Rich/Textual bug (see #top-bar-right's
        # CSS comment) — a fixed width sidesteps it, but the actual text
        # length varies (cpu/mem readings may be absent). cell_len (not
        # len()) counts *display* cells, matching Textual's own width
        # layout, so this stays exact even with a wide/emoji glyph — no more
        # oversized static guess leaving a gap before the card's edge.
        right.styles.width = cell_len(line)
        right.update(line)

    def set_workspace(self, name: str | None, session: str | None = None) -> None:
        """Keep current workspace and its foreground-agent cue visible."""
        self._workspace_name = name
        self._session = session
        self._painted_workspace = None
        self.refresh_workspace_indicator()

    def refresh_workspace_indicator(self) -> None:
        """Refresh the quiet pane-process cue without claiming model activity."""
        agent = session_agent_label(self._session)
        if self._workspace_name:
            prefix = f"• {agent}  " if agent else ""
            line = f"{prefix}{self._workspace_name}  ⌄"
        else:
            line = "Select workspace  ⌄"
        if line == self._painted_workspace:
            return
        self._painted_workspace = line
        trigger = self.query_one("#workspace-trigger", Static)
        trigger.styles.width = cell_len(line) + 2
        trigger.update(line)
        trigger.set_class(bool(agent), "agent-active")
        trigger.tooltip = (
            f"Current pane runs {agent}; choose or inspect workspaces (F4)"
            if agent
            else "Choose a workspace and inspect its projects (F4)"
        )
