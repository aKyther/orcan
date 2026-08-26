"""One-shot first-run tips overlay (IDE welcome / command palette hint)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Static

from orcan_cockpit.onboarding import mark_onboarding_seen

_CSS = """
FirstRunModal {
    align: center middle;
    background: rgba(0, 0, 0, 0.45);
}

#first-run-dialog {
    width: 64;
    height: auto;
    background: #0d1520;
    border: solid #5eead4;
    padding: 1 2;
}

.first-run-title {
    color: #5eead4;
    text-style: bold;
}

.first-run-body {
    color: #c8d3e0;
    margin-top: 1;
}

.first-run-footer {
    color: #64748b;
    margin-top: 1;
}
"""


class FirstRunModal(ModalScreen[None]):
    CSS = _CSS
    BINDINGS = [
        ("escape", "dismiss_seen", "Close"),
        ("enter", "dismiss_seen", "Close"),
        ("space", "dismiss_seen", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="first-run-dialog"):
            yield Static("Welcome to orcan cockpit", classes="first-run-title")
            yield Static(
                "F5  Peek brief / next pending note\n"
                "Ctrl+P  Command palette (review, split, tasks)\n"
                "F2  Assertions · Review = lasting context notes\n"
                "\n"
                "Reflection (~20 turns) proposes short facts — you say y/n.\n"
                "Preview busy fixtures are fake scroll data, not session facts.\n"
                "No Claude Code → automation stays off; Review still works.",
                classes="first-run-body",
            )
            yield Static("Enter / Esc — dismiss (won't show again)", classes="first-run-footer")

    def action_dismiss_seen(self) -> None:
        mark_onboarding_seen()
        self.dismiss(None)
