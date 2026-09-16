"""The bottom status bar widget — thin Textual shim over status.py's pure,
host-testable formatting. Workspace identity only — CPU/RAM/clock
live in the top bar (top_bar.py) instead."""

from __future__ import annotations

import asyncio
from functools import partial
from pathlib import Path

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from orcan_cockpit.status import Tier, format_status_line, git_branch
from orcan_cockpit.tmux_chrome import session_breadcrumb

# A status refresh can call both git and tmux. Keep these external probes out
# of the terminal's frequent paint cycle; state setters still refresh at once.
_REFRESH_INTERVAL_S = 8.0


class StatusBar(Widget):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.workspace_name: str | None = None
        self.workspace_root: Path | None = None
        self.session: str | None = None
        self.tier: Tier = "full"
        self.focus: str | None = None
        self._painted_line: str | None = None

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

    def clear_workspace(self) -> None:
        """Remove stale identity when a requested tmux session cannot open."""
        self.workspace_name = None
        self.workspace_root = None
        self.session = None
        self.refresh_status()

    def set_tier(self, tier: Tier) -> None:
        if tier != self.tier:
            self.tier = tier
            self.refresh_status()

    def set_focus(self, focus: str | None) -> None:
        if focus != self.focus:
            self.focus = focus
            self.refresh_status()

    def refresh_status(self) -> None:
        # Compact/mobile tiers do not render branch or tmux breadcrumb. Avoid
        # spawning their probes entirely there — work that cannot be seen is
        # pure latency on a small terminal.
        detailed = self.tier == "full"
        workspace_name = self.workspace_name
        workspace_root = self.workspace_root
        session = self.session
        tier = self.tier
        focus = self.focus
        if not detailed or (workspace_root is None and session is None):
            line = format_status_line(
                tier=tier,
                workspace=workspace_name,
                branch="",
                session=session,
                breadcrumb="",
                focus=focus,
            )
            if line != self._painted_line:
                self._painted_line = line
                self.query_one("#status-body", Static).update(line)
            return
        self.run_worker(
            partial(
                self._resolve_status,
                detailed=detailed,
                workspace_name=workspace_name,
                workspace_root=workspace_root,
                session=session,
                tier=tier,
                focus=focus,
            ),
            group="status-refresh",
            exclusive=True,
            exit_on_error=False,
        )

    async def _resolve_status(
        self,
        *,
        detailed: bool,
        workspace_name: str | None,
        workspace_root: Path | None,
        session: str | None,
        tier: Tier,
        focus: str | None,
    ) -> None:
        """Read Git/tmux outside the UI loop, then paint one current result."""
        branch_task = (
            asyncio.to_thread(git_branch, str(workspace_root))
            if detailed and workspace_root
            else _empty_probe()
        )
        breadcrumb_task = (
            asyncio.to_thread(session_breadcrumb, session)
            if detailed and session
            else _empty_probe()
        )
        branch, crumb = await asyncio.gather(branch_task, breadcrumb_task)
        if (
            self.workspace_name != workspace_name
            or self.workspace_root != workspace_root
            or self.session != session
            or self.tier != tier
            or self.focus != focus
        ):
            return
        line = format_status_line(
            tier=tier,
            workspace=workspace_name,
            branch=branch,
            session=session,
            breadcrumb=crumb,
            focus=focus,
        )
        if line == self._painted_line:
            return
        self._painted_line = line
        self.query_one("#status-body", Static).update(line)


async def _empty_probe() -> str:
    """Keep optional status probes composable without a special await path."""
    return ""
