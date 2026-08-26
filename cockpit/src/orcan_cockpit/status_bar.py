"""The bottom status bar widget — thin Textual shim over status.py's pure
formatting, matching the panel.py-imports-actions.py split (framework code
here, host-testable logic there). Workspace identity only — CPU/RAM/clock
live in the top bar (top_bar.py) instead."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

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
        branch = git_branch(str(self.workspace_root)) if self.workspace_root else ""
        line = format_status_line(
            tier=self.tier,
            workspace=self.workspace_name,
            branch=branch,
            session=self.session,
        )
        self.query_one("#status-body", Static).update(line)
