"""Session-brief preview without leaving the cockpit."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Button, Static

from orcan_cockpit.peek import build_peek_text
from orcan_cockpit.sheet_modal import SHEET_CSS, SheetModal

_CSS = SHEET_CSS + """
#peek-dialog {
    width: 72;
}

.peek-heading {
    color: #c7b1e2;
    text-style: bold;
    margin-top: 1;
}

.peek-heading:first-child {
    margin-top: 0;
}

.peek-body {
    color: #e2ddea;
}

.peek-footer {
    color: #948ba3;
    margin-top: 1;
}
"""


class PeekModal(SheetModal):
    """Floating session-brief preview."""

    CSS = _CSS
    BINDINGS = [
        ("escape", "dismiss_close", "Close"),
        ("enter", "dismiss_close", "Close"),
    ]

    def __init__(self, workspace_root: str | Path, **kwargs) -> None:
        super().__init__(**kwargs)
        self.workspace_root = Path(workspace_root)

    def compose(self) -> ComposeResult:
        text = build_peek_text(self.workspace_root)
        with Container(classes="sheet", id="peek-dialog"):
            with Horizontal(classes="sheet-header"):
                yield Static("SESSION BRIEF", classes="sheet-title")
                yield Button("Close", id="peek-close", classes="sheet-close")
            with VerticalScroll():
                yield Static(text, classes="peek-body")
                yield Static(
                    "Enter / Esc to close",
                    classes="peek-footer",
                )

    def action_dismiss_close(self) -> None:
        self.dismiss("close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "peek-close":
            self.dismiss("close")
