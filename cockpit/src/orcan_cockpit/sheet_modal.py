"""Shared, quiet chrome for Cockpit's temporary information sheets."""

from __future__ import annotations

from textual.screen import ModalScreen


SHEET_CSS = """
SheetModal {
    align: center middle;
    background: rgba(0, 0, 0, 0.4);
}

.sheet {
    height: auto;
    max-height: 80%;
    background: #211c2b;
    border-left: solid #ad91d0;
    padding: 1 2;
}

.sheet-header {
    layout: horizontal;
    height: 1;
    margin-bottom: 1;
}

.sheet-title {
    width: 1fr;
    color: #c7b1e2;
    text-style: bold;
}

.sheet-close {
    width: auto;
    min-width: 0;
    height: 1;
    padding: 0 1;
    border: none;
    background: #2a2237;
    color: #c7b1e2;
}

.sheet-close:hover, .sheet-close:focus {
    background: #342a44;
    color: #e2ddea;
}

SheetModal.sheet-full {
    align: left top;
}

SheetModal.sheet-full .sheet {
    width: 1fr;
    height: 1fr;
    max-height: 100%;
    border-left: none;
    background: #17131f;
}
"""


class SheetModal(ModalScreen):
    """A centered sheet on desktop and a full screen on a phone."""

    def on_mount(self) -> None:
        self.set_class(self.size.width < 90, "sheet-full")
