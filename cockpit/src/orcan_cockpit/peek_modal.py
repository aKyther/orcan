"""Peek modal — brief + first pending note without a tmux split (IDE peek).

Dismiss result: ``None``/``\"close\"`` = just close; ``\"review\"`` = open
full ``orcan-context-review`` (Enter / r).
"""

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
    background: #0d1520;
    border: solid #a78bfa;
    padding: 1 2;
}

.peek-heading {
    color: #a78bfa;
    text-style: bold;
    margin-top: 1;
}

.peek-heading:first-child {
    margin-top: 0;
}

.peek-body {
    color: #c8d3e0;
}

.peek-footer {
    color: #64748b;
    margin-top: 1;
}
"""


class PeekModal(ModalScreen[str | None]):
    """Floating peek — Escape closes; Enter / r starts Review."""

    CSS = _CSS
    BINDINGS = [
        ("escape", "dismiss_close", "Close"),
        ("p", "dismiss_close", "Close"),
        ("enter", "dismiss_review", "Review"),
        ("r", "dismiss_review", "Review"),
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
                    "Enter / r → Review · Esc to close",
                    classes="peek-footer",
                )

    def action_dismiss_close(self) -> None:
        self.dismiss("close")

    def action_dismiss_review(self) -> None:
        self.dismiss("review")
