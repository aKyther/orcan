"""Session-brief preview without leaving the cockpit."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from orcan_cockpit.peek import build_peek_text

_CSS = """
PeekModal {
    align: center middle;
    background: rgba(0, 0, 0, 0.4);
}

#peek-dialog {
    width: 72;
    height: auto;
    max-height: 80%;
    background: #17131d;
    border-left: solid #9b87b8;
    padding: 1 2;
}

.peek-heading {
    color: #b9a7d6;
    text-style: bold;
    margin-top: 1;
}

.peek-heading:first-child {
    margin-top: 0;
}

.peek-body {
    color: #d8d2e2;
}

.peek-footer {
    color: #756f82;
    margin-top: 1;
}
"""


class PeekModal(ModalScreen[str | None]):
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
        with Container(id="peek-dialog"):
            with VerticalScroll():
                yield Static("PEEK", classes="peek-heading")
                yield Static(text, classes="peek-body")
                yield Static(
                    "Enter / Esc to close",
                    classes="peek-footer",
                )

    def action_dismiss_close(self) -> None:
        self.dismiss("close")
