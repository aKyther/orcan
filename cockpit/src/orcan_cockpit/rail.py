"""Utility rail: a row of icon buttons (activity-bar style) that launches
real tools rather than reimplementing them — assertions (reveals + focuses
the ASSERTIONS section at the bottom of the left panel — see activity.py),
Git (a tmux display-popup running lazygit, see actions.py), shortcuts (the
ShortcutsModal overlay). Lives at the left edge of app.py's top bar
(#top-bar) — a plain Widget with `layout: horizontal` set on #rail in
app.py's CSS, not a dedicated Horizontal container here, so this class
doesn't need to know or care which orientation it's mounted in.

No workspaces/hamburger button here anymore — that toggle moved to a
dedicated edge-of-panel arrow (#sidebar-toggle in app.py), a more standard
IDE affordance than a rail icon for a collapsible sidebar."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button

_TOOL_BY_BUTTON_ID = {
    "rail-assertions": "assertions",
    "rail-git": "git",
    "rail-shortcuts": "shortcuts",
}


class UtilityRail(Widget):
    can_focus = True

    class ToolSelected(Message):
        def __init__(self, tool: str) -> None:
            self.tool = tool
            super().__init__()

    def compose(self) -> ComposeResult:
        yield Button("🔔", id="rail-assertions")
        yield Button("⎇", id="rail-git")
        yield Button("?", id="rail-shortcuts")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        tool = _TOOL_BY_BUTTON_ID.get(event.button.id or "")
        if tool:
            self.post_message(self.ToolSelected(tool))

    def set_pending_count(self, count: int) -> None:
        button = self.query_one("#rail-assertions", Button)
        button.label = f"🔔{count}" if count else "🔔"
