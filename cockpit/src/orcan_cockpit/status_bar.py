"""The bottom status bar widget — thin Textual shim over status.py's pure
formatting, matching the panel.py-imports-actions.py split (framework code
here, host-testable logic there). Workspace identity only — CPU/RAM/clock
live in the top bar (top_bar.py) instead."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from orcan.context_inbox import pending_summary
from orcan_cockpit.status import Tier, format_status_line, git_branch

_REFRESH_INTERVAL_S = 3.0


class StatusBar(Widget):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.workspace_name: str | None = None
        self.workspace_root: Path | None = None
        self.session: str | None = None
        self.tier: Tier = "full"

    def compose(self) -> ComposeResult:
        yield Static(id="status-body")

    def on_mount(self) -> None:
        # Clicking anywhere on this bar reveals ASSERTIONS (MainScreen.
        # on_click → _reveal_assertions) — same destination as the rail's 🔔
        # button. It looked like a quick-path already (same glyph as the
        # clickable rail bell); making it one instead of just explaining in
        # a tooltip why it wasn't matches what it already visually promised.
        self.query_one("#status-body", Static).tooltip = (
            "Workspace · git branch · tmux session · 🔔 pending assertions — "
            "click to review them"
        )
        self.refresh_status()
        self.set_interval(_REFRESH_INTERVAL_S, self.refresh_status)

    def set_workspace(self, name: str, root: str, session: str) -> None:
        self.workspace_name = name
        self.workspace_root = Path(root)
        self.session = session
        self.refresh_status()

    def set_tier(self, tier: Tier) -> None:
        if tier != self.tier:
            self.tier = tier
            self.refresh_status()

    def refresh_status(self) -> None:
        pending = pending_summary(self.workspace_root)["count"] if self.workspace_root else 0
        branch = git_branch(str(self.workspace_root)) if self.workspace_root else ""
        line = format_status_line(
            tier=self.tier,
            workspace=self.workspace_name,
            branch=branch,
            session=self.session,
            pending=pending,
        )
        self.query_one("#status-body", Static).update(line)
