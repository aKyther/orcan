"""Compact utility rail for help and a pointer-safe return to the host."""

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button

from orcan_cockpit.jobs_modal import read_pulse


class UtilityRail(Widget):
    can_focus = True
    REFRESH_SECONDS = 15

    class ToolSelected(Message):
        def __init__(self, tool: str) -> None:
            self.tool = tool
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._tier = "full"
        self._polling = False

    def compose(self) -> ComposeResult:
        yield Button(
            "?", id="rail-shortcuts", tooltip="Keyboard shortcuts (app + tmux)"
        )
        yield Button("Tasks", id="rail-jobs", tooltip="Needs attention, background jobs and workspaces")
        yield Button(
            "Exit",
            id="rail-exit",
            tooltip="Close Cockpit and return to the host terminal",
        )

    def on_mount(self) -> None:
        self.refresh_attention()
        self.set_interval(self.REFRESH_SECONDS, self.refresh_attention)

    def refresh_attention(self) -> None:
        if self._polling:
            return
        self._polling = True
        self.run_worker(self._read_attention(), group="attention-pulse", exclusive=True, exit_on_error=False)

    async def _read_attention(self) -> None:
        try:
            low_space = False
            try:
                value = await read_pulse()
                count = value["attention_count"]
                ready = value["storage"]["ready"]
                if type(count) is not int or count < 0 or (ready is not None and type(ready) is not bool):
                    raise ValueError("Invalid pulse")
                low_space = ready is False
                label = f"Tasks · {count}" + (" !" if ready is False else " ?" if ready is None else "")
                tooltip = f"{count} jobs need attention"
                if ready is False:
                    tooltip += " · Low disk space; inspect orcan storage"
                elif ready is None:
                    tooltip += " · Disk status unavailable"
            except (OSError, ValueError, TimeoutError, KeyError, TypeError):
                label, tooltip = "Tasks · ?", "Task summary unavailable; open Tasks for details"
            button = self.query_one("#rail-jobs", Button)
            if str(button.label) != label:
                button.label = label
            button.tooltip = tooltip
            button.set_class(low_space, "disk-low")
        finally:
            self._polling = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "rail-shortcuts":
            self.post_message(self.ToolSelected("shortcuts"))
        elif event.button.id == "rail-jobs":
            self.post_message(self.ToolSelected("jobs"))
        elif event.button.id == "rail-exit":
            self.post_message(self.ToolSelected("exit"))

    def set_tier(self, tier: str) -> None:
        self._tier = tier
        button = self.query_one("#rail-shortcuts", Button)
        button.label = "? Help" if tier == "full" else "?"
