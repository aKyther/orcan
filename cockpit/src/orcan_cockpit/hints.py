"""Contextual keyboard-hint strip: one line under the terminal, showing
2-5 relevant bindings for whatever currently has focus. Pulls from
shortcuts.SHORTCUTS (via hints_for()) — the same manifest the shortcuts
overlay and standalone tmux popup render, so hints can't drift from the
real, active bindings.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from orcan_cockpit.shortcuts import Context, hints_for


class HintStrip(Widget):
    def compose(self) -> ComposeResult:
        yield Static(id="hint-body")

    def set_target(self, context: Context) -> None:
        hints = hints_for(context)
        text = "  ·  ".join(hints) if hints else ""
        self.query_one("#hint-body", Static).update(f"⌨  {text}" if text else "")
