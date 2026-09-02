"""Top bar: utility rail icons (left) + system metrics (right, CPU/RAM/
clock). Sits above #main-row, full width, one row — replaces both the old
right-hand icon column and the identity+metrics row tmux's own status.conf
used to render (trimmed there as redundant — see that file's header
comment)."""

from __future__ import annotations

from rich.cells import cell_len
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from orcan_cockpit.rail import UtilityRail
from orcan_cockpit.status import format_top_bar_right, now_hhmm, read_loadavg, read_mem_percent

_REFRESH_INTERVAL_S = 3.0


class TopBar(Widget):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._painted_metrics: str | None = None

    def compose(self) -> ComposeResult:
        # 🌀 (cyclone) not ◆ — orcan's own branding is elemental (hurricane/
        # whirlwind), and this is a plain, old (Unicode 6.0) emoji that
        # renders without needing a Nerd Font, matching the ttyd-safe-fonts
        # constraint documented in Terminal UI. Static, never updated after
        # compose, so width:auto here doesn't hit the "duplicate last char"
        # Rich/Textual bug that content changing via .update() triggers
        # elsewhere (see #top-bar-right's own comment for that one).
        yield Static("🌀 orcan", id="top-bar-identity")
        yield Static("○ Select workspace  ⌄", id="workspace-trigger")
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
            "💻 system load average · 🧠 memory used · 🕐 clock"
        )
        self.query_one("#top-bar-identity", Static).tooltip = "About orcan cockpit"
        self.query_one("#workspace-trigger", Static).tooltip = "Open workspaces (F4)"
        self.set_workspace(None)
        self.refresh_metrics()
        self.set_interval(_REFRESH_INTERVAL_S, self.refresh_metrics)

    def refresh_metrics(self) -> None:
        line = format_top_bar_right(cpu=read_loadavg(), mem=read_mem_percent(), clock=now_hhmm())
        if line == self._painted_metrics:
            return
        self._painted_metrics = line
        right = self.query_one("#top-bar-right", Static)
        # width:auto also has a real Rich/Textual bug (see #top-bar-right's
        # CSS comment) — a fixed width sidesteps it, but the actual text
        # length varies (cpu/mem readings may be absent). cell_len (not
        # len()) counts *display* cells, matching Textual's own width
        # layout, so this stays exact even with a wide/emoji glyph — no more
        # oversized static guess leaving a gap before the card's edge.
        right.styles.width = cell_len(line)
        right.update(line)

    def set_workspace(self, name: str | None) -> None:
        """Keep the current context visible while the drawer is closed."""
        line = f"● {name}  ⌄" if name else "○ Select workspace  ⌄"
        trigger = self.query_one("#workspace-trigger", Static)
        trigger.styles.width = cell_len(line) + 2
        trigger.update(line)
