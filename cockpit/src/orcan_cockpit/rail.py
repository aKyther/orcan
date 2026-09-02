"""Compact utility rail containing the cockpit help entry point."""

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button


class UtilityRail(Widget):
    can_focus = True

    class ToolSelected(Message):
        def __init__(self, tool: str) -> None:
            self.tool = tool
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._tier = "full"

    def compose(self) -> ComposeResult:
        yield Button("?", id="rail-shortcuts", tooltip="Keyboard shortcuts (app + tmux)")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "rail-shortcuts":
            self.post_message(self.ToolSelected("shortcuts"))

    def set_tier(self, tier: str) -> None:
        self._tier = tier
        button = self.query_one("#rail-shortcuts", Button)
        button.label = "? Help" if tier == "full" else "?"
