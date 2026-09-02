"""In-cockpit shortcut overlay (F1 / `?`) — reads the same SHORTCUTS manifest
as the standalone tmux-popup renderer (shortcuts_cli.py), via the shared
format_row() helper, so the two can't show different bindings.

Shortcuts only — no product identity/About here. That used to be bundled
into this same modal, but "what are the keybindings" and "what is this
app" are two different questions a user asks at two different moments;
About now lives in its own screen (about_modal.py), reachable by clicking
the "🌀 orcan" wordmark, not by pressing F1/?.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from orcan_cockpit.shortcuts import BROWSER_KEY_LIMIT, EMBED_DISCLAIMER, format_row, grouped_by_layer

_CSS = """
ShortcutsModal {
    align: center middle;
    background: rgba(0, 0, 0, 0.4);
}

#shortcuts-dialog {
    width: 74;
    height: auto;
    max-height: 80%;
    background: #17131d;
    border-left: solid #9b87b8;
    padding: 1;
}

.shortcuts-heading {
    color: #b9a7d6;
    text-style: bold;
    margin-top: 1;
}

.shortcuts-heading:first-child {
    margin-top: 0;
}

.shortcuts-footer {
    color: #756f82;
    margin-top: 1;
}
"""


class ShortcutsModal(ModalScreen[None]):
    """Floating shortcut reference — Escape or `?` dismisses."""

    CSS = _CSS
    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("f1", "dismiss", "Close"),
        ("question_mark", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        groups = grouped_by_layer()
        with Container(id="shortcuts-dialog"):
            with VerticalScroll():
                yield Static("APP", classes="shortcuts-heading")
                for shortcut in groups["app"]:
                    yield Static(format_row(shortcut))
                yield Static("TMUX (prefix = Ctrl+Space)", classes="shortcuts-heading")
                for shortcut in groups["tmux"]:
                    yield Static(format_row(shortcut))
                yield Static(EMBED_DISCLAIMER, classes="shortcuts-footer")
                yield Static(BROWSER_KEY_LIMIT, classes="shortcuts-footer")
                yield Static("Esc / ? to close", classes="shortcuts-footer")

    def action_dismiss(self, result: None = None) -> None:
        self.dismiss(result)
