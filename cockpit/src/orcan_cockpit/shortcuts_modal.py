"""In-cockpit shortcut overlay (F1 / `?`) — reads the same SHORTCUTS manifest
as the standalone tmux-popup renderer (shortcuts_cli.py), via the shared
format_row() helper, so the two can't show different bindings.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from orcan_cockpit.shortcuts import (
    BROWSER_KEY_LIMIT,
    DOCS_URL,
    EMBED_DISCLAIMER,
    PRODUCT_NAME,
    PRODUCT_SUMMARY,
    format_row,
    grouped_by_layer,
    product_version,
)

_CSS = """
ShortcutsModal {
    align: center middle;
    background: rgba(0, 0, 0, 0.4);
}

#shortcuts-dialog {
    width: 74;
    height: auto;
    max-height: 80%;
    background: #0d1520;
    border: solid #5eead4;
    padding: 1 2;
}

.shortcuts-heading {
    color: #5eead4;
    text-style: bold;
    margin-top: 1;
}

.shortcuts-heading:first-child {
    margin-top: 0;
}

.shortcuts-footer {
    color: #64748b;
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
                yield Static("ABOUT", classes="shortcuts-heading")
                yield Static(f"{PRODUCT_NAME} · v{product_version()}")
                yield Static(PRODUCT_SUMMARY)
                # Quotes around the URL are required, not decorative:
                # Textual's own markup engine (Content.from_markup, not
                # Rich's) fails to parse an unquoted "://" inside a tag
                # value with MarkupError — confirmed via real pty run, which
                # crashed the whole modal. Short display text ("Full docs
                # →", matching activity.py's "Learn more →" doc link)
                # because this dialog is only 74 cols wide.
                yield Static(f'[link="{DOCS_URL}"]Full docs →[/link]')
                yield Static(EMBED_DISCLAIMER, classes="shortcuts-footer")
                yield Static(BROWSER_KEY_LIMIT, classes="shortcuts-footer")
                yield Static("Esc / ? to close", classes="shortcuts-footer")

    def action_dismiss(self, result: None = None) -> None:
        self.dismiss(result)
