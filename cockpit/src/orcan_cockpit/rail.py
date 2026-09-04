"""Compact utility rail for help and a pointer-safe return to the host."""

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
        yield Button("Exit", id="rail-exit", tooltip="Close Cockpit and return to the host terminal")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "rail-shortcuts":
            self.post_message(self.ToolSelected("shortcuts"))
        elif event.button.id == "rail-exit":
            self.post_message(self.ToolSelected("exit"))

    def set_tier(self, tier: str) -> None:
        self._tier = tier
        button = self.query_one("#rail-shortcuts", Button)
        button.label = "? Help" if tier == "full" else "?"
