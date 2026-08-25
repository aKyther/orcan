"""Side panel: pending Context Assertions (count + oldest age) and last
reflection status for the attached workspace, plus the "run context review"
action. Refreshed on file changes (watchfiles) rather than a poll interval —
the concrete "podpowiadacz" ask from the design discussion.

The pending-summary/reflection-status logic lives in the vendored, stdlib-only
orcan.context_inbox (shared with orcan-context-review — see cli.py for where
/usr/local/lib is added to sys.path); this module is just the thin Textual
rendering + focus shim over it and over actions.py, matching
scripts/repository/context_tui.py's established split.
"""

from __future__ import annotations

from pathlib import Path

from textual import events
from textual.widget import Widget
from textual.widgets import Static

from orcan.context_inbox import format_pending_age, pending_summary, reflection_status
from orcan_cockpit.actions import run_context_review_popup

try:
    from watchfiles import awatch
except ImportError:  # pragma: no cover - always present in the cockpit venv
    awatch = None


class SidePanel(Widget):
    """Docked info + actions panel for one workspace."""

    can_focus = True

    def __init__(self, workspace_root: str, session: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.workspace_root = Path(workspace_root)
        self.session = session

    def compose(self):
        yield Static(id="panel-body")

    def on_mount(self) -> None:
        self.refresh_summary()
        self.run_worker(self._watch_loop(), exclusive=True)

    def refresh_summary(self) -> None:
        summary = pending_summary(self.workspace_root)
        age = format_pending_age(summary["oldest_mtime"])
        lines = [
            f"pending assertions: {summary['count']}" + (f" (oldest {age})" if age else ""),
            reflection_status(self.workspace_root),
            "",
            "[r] run context review",
            "",
            "F2 back to terminal",
        ]
        self.query_one("#panel-body", Static).update("\n".join(lines))

    def on_key(self, event: events.Key) -> None:
        if event.key == "r":
            run_context_review_popup(self.session)
            event.stop()

    async def _watch_loop(self) -> None:
        if awatch is None:
            return
        watch_dir = self.workspace_root / ".orcan"
        watch_dir.mkdir(parents=True, exist_ok=True)
        async for _changes in awatch(watch_dir):
            self.refresh_summary()
