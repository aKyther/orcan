"""Utility rail: a row of icon buttons (activity-bar style) that launches
real tools rather than reimplementing them — assertions (reveals + focuses
the ASSERTIONS section at the bottom of the left panel — see activity.py),
shortcuts (the ShortcutsModal overlay). Lives at the left edge of app.py's
top bar (#top-bar) — a plain Widget with `layout: horizontal` set on #rail
in app.py's CSS, not a dedicated Horizontal container here, so this class
doesn't need to know or care which orientation it's mounted in.

No workspaces/hamburger button here anymore — that toggle moved to a
dedicated edge-of-panel arrow (#sidebar-toggle in app.py), a more standard
IDE affordance than a rail icon for a collapsible sidebar. No Git/lazygit
button either (removed on request — lazygit stays reachable via the `lg`
shell alias inside the terminal itself, so a dedicated cockpit shortcut for
it was redundant)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button

_TOOL_BY_BUTTON_ID = {
    "rail-assertions": "assertions",
    "rail-shortcuts": "shortcuts",
}

# Icon-only at every tier (bare glyphs give no clue what they do — this was
# reported as unclear); text is appended only at the "full" terminal-width
# tier (see status.tier_for_width) so compact/minimal keep the original
# narrow footprint. Tooltips (Textual's Button.tooltip, shown on hover) carry
# the fuller explanation regardless of tier, since a mouse-hover affordance
# doesn't cost any layout width.
_ICON = {"assertions": "🔔", "shortcuts": "?"}
_TEXT = {"assertions": "Assertions", "shortcuts": "Help"}
_TOOLTIP = {
    "assertions": "Problems — pending assertions, reflection errors, dirty repos",
    "shortcuts": "Keyboard shortcuts (app + tmux)",
}
_PULSE_INTERVAL_S = 0.85


class UtilityRail(Widget):
    can_focus = True

    class ToolSelected(Message):
        def __init__(self, tool: str) -> None:
            self.tool = tool
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._tier = "full"
        self._pending_count = 0
        self._problems_tooltip = _TOOLTIP["assertions"]

    def compose(self) -> ComposeResult:
        yield Button(_ICON["assertions"], id="rail-assertions", tooltip=_TOOLTIP["assertions"])
        yield Button(_ICON["shortcuts"], id="rail-shortcuts", tooltip=_TOOLTIP["shortcuts"])

    def on_mount(self) -> None:
        self._refresh_labels()
        self.set_interval(_PULSE_INTERVAL_S, self._pulse_tick)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        tool = _TOOL_BY_BUTTON_ID.get(event.button.id or "")
        if tool:
            self.post_message(self.ToolSelected(tool))

    def set_pending_count(self, count: int, *, tooltip: str | None = None) -> None:
        """*count* is the aggregated problems badge (pending + errors + dirty)."""
        tooltip_changed = tooltip is not None and tooltip != self._problems_tooltip
        if count == self._pending_count and not tooltip_changed:
            return
        self._pending_count = count
        if tooltip is not None:
            self._problems_tooltip = tooltip
        self._refresh_labels()
        if not count:
            self.query_one("#rail-assertions", Button).remove_class("pending-pulse")

    def set_tier(self, tier: str) -> None:
        self._tier = tier
        self._refresh_labels()

    def _pulse_tick(self) -> None:
        # Amber blink when something awaits attention — catchy without a
        # second status surface. Off when problems count is zero.
        btn = self.query_one("#rail-assertions", Button)
        if self._pending_count <= 0:
            btn.remove_class("pending-pulse")
            return
        btn.toggle_class("pending-pulse")

    def _refresh_labels(self) -> None:
        wide = self._tier == "full"
        bell = _ICON["assertions"]
        if self._pending_count:
            # Amber, not the default text color — a problems count is an
            # attention signal, and it's the one warm accent against an
            # otherwise cool navy/cyan/violet bar (flagged as too
            # monochrome in review). Button.label parses markup (Textual's
            # Content.from_markup) same as Static.
            bell += f" [#fbbf24]{self._pending_count}[/]"
        if wide:
            bell += f" {_TEXT['assertions']}"
        btn = self.query_one("#rail-assertions", Button)
        btn.label = bell
        btn.tooltip = self._problems_tooltip
        icon = _ICON["shortcuts"]
        label = f"{icon} {_TEXT['shortcuts']}" if wide else icon
        self.query_one("#rail-shortcuts", Button).label = label
