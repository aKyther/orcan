"""Textual cockpit app: workspace picker → embedded live tmux session with a
side panel for pending Context Assertions + actions. This is what cli.py
launches on a real tty.

tmux stays the real session/window/pane engine throughout: WorkspaceScreen
only owns the outer pty (PtyTerminal spawns `tmux attach` as its child) and
renders a side panel around it. Nothing here re-implements tmux's own
session/window/pane logic.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen

from orcan_cockpit.panel import SidePanel
from orcan_cockpit.picker import WorkspacePicker, bootstrap_workspace
from orcan_cockpit.pty_terminal import PtyTerminal


class WorkspaceScreen(Screen):
    """One attached workspace: embedded tmux + side panel."""

    BINDINGS = [("f2", "toggle_panel", "Toggle panel")]

    def __init__(self, row: dict) -> None:
        super().__init__()
        self.row = row
        self._panel_visible = True

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield PtyTerminal(
                ["tmux", "attach", "-t", f"={self.row['session']}"],
                id="terminal",
            )
            yield SidePanel(self.row["root"], self.row["session"], id="panel")

    def action_toggle_panel(self) -> None:
        panel = self.query_one("#panel", SidePanel)
        self._panel_visible = not self._panel_visible
        panel.display = self._panel_visible
        if self._panel_visible:
            panel.focus()
        else:
            self.query_one("#terminal", PtyTerminal).focus()


class CockpitApp(App):
    """ttyd's PTY command when a real tty is attached — see cli.py."""

    TITLE = "orcan"
    CSS = """
    #terminal { width: 3fr; }
    #panel { width: 1fr; border-left: solid $primary; padding: 1; }
    """

    def on_mount(self) -> None:
        self.push_screen(WorkspacePicker())

    def open_workspace(self, row: dict) -> None:
        bootstrap = bootstrap_workspace(row)
        if bootstrap.returncode != 0:
            self.notify(f"Could not bootstrap session {row['session']!r}", severity="error")
            return
        self.push_screen(WorkspaceScreen(row))


def run_cockpit() -> int:
    CockpitApp().run()
    return 0
