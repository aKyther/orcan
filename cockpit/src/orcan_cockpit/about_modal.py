"""About screen — product identity only (name, version, docs link).

Deliberately separate from ShortcutsModal (F1/?): "what is this app" and
"what are the keybindings" are different questions asked at different
moments, and this one doesn't try to explain how the product works — that
belongs in docs (linked below), not repeated in the UI. Reachable by
clicking the "🌀 orcan" wordmark in the top bar (see app.py's on_click).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Static

from orcan_cockpit.shortcuts import DOCS_URL, PRODUCT_NAME, product_version

_CSS = """
AboutModal {
    align: center middle;
    background: rgba(0, 0, 0, 0.4);
}

#about-dialog {
    width: 44;
    height: auto;
    background: #211c2b;
    border-left: solid #ad91d0;
    padding: 1;
}

#about-name {
    color: #c7b1e2;
    text-style: bold;
}

#about-footer {
    color: #948ba3;
    margin-top: 1;
}
"""


class AboutModal(ModalScreen[None]):
    """Product identity only — Escape dismisses."""

    CSS = _CSS
    BINDINGS = [("escape", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        with Container(id="about-dialog"):
            yield Static(f"{PRODUCT_NAME} · v{product_version()}", id="about-name")
            # Quotes around the URL are required, not decorative: Textual's
            # own markup engine (Content.from_markup, not Rich's) fails to
            # parse an unquoted "://" inside a tag value with MarkupError —
            # confirmed via a real pty run that crashed on this exact line
            # before the quotes were added.
            yield Static(f'[link="{DOCS_URL}"]Full docs →[/link]')
            yield Static("Esc to close", id="about-footer")

    def action_dismiss(self, result: None = None) -> None:
        self.dismiss(result)
