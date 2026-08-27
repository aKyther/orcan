"""Bottom half of the left column: pending Context Assertions (count +
oldest age), last reflection status, automation pause state, and the
actions on them ("[r] run context review", "[p] pause/resume automation").
Top half is WorkspaceList (picker.py) — together they make up #workspaces
in app.py.

This used to be split across two surfaces (a glance-only strip here, plus a
separate actionable SidePanel docked on the right) — consolidated into one
so there's a single place assertions live and a single computation, not two
that could disagree. Refreshed on file changes (watchfiles) rather than a
poll interval — the concrete "podpowiadacz" ask from the design discussion.

The pending-summary/reflection-status logic lives in the vendored, stdlib-only
orcan.context_inbox (shared with orcan-context-review — see cli.py for where
/usr/local/lib is added to sys.path); this module is just the thin Textual
rendering + focus shim over it and over actions.py, matching
scripts/repository/context_tui.py's established split.
"""

from __future__ import annotations

import time
from pathlib import Path

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Static

from orcan.context_inbox import format_pending_age, pending_summary, reflection_status
from orcan_cockpit.actions import (
    automation_state,
    automation_status_lines,
    run_context_review_popup,
    toggle_automation_enabled,
    toggle_automation_pause,
)
from orcan_cockpit.problems import pending_across_roots, problems_summary
from orcan_cockpit.reflection_feedback import last_batch_feedback
from orcan_cockpit.timeline import format_timeline, recent_decisions
from orcan_cockpit.tmux_chrome import list_agent_panes, read_pinned_pane

try:
    from orcan.automation import claude_on_path, sync_automation_to_claude_availability
except ImportError:  # pragma: no cover
    def claude_on_path() -> bool:
        return True

    def sync_automation_to_claude_availability() -> dict:
        return {}

try:
    from watchfiles import awatch
except ImportError:  # pragma: no cover - always present in the cockpit venv
    awatch = None

PLACEHOLDER = (
    "[#a78bfa]🌀[/] Pick a workspace to see pending assertions.\n"
    "[#64748b]F2 toggles this panel[/]"
)

# Short enough to fit on one line at this card's real usable width (~27
# cols after border+padding, confirmed via real pty render) — the original
# wording wrapped to 3 lines, which was flagged as making the card
# noticeably bulkier than before this subtitle existed.
SUBTITLE = "Proposed, awaiting review"

# Real, hosted docs page (docs/en/ideas/context-assertions.md, published via
# GitHub Pages — see docs/llms.txt) rendered as a clickable OSC8 hyperlink
# (Textual's own markup engine, Content.from_markup, interpreted because
# Static defaults to markup=True). Modern terminals (iTerm2/kitty/WezTerm/
# Windows Terminal, and ttyd's xterm.js — orcan's two transports) render
# this as a real clickable link; terminals without OSC8 support just show
# the plain text, no markup leaks through.
DOCS_URL = "https://akyther.github.io/orcan/latest/ideas/context-assertions/"


class WorkspaceActivity(Widget):
    """Docked info + actions section — persistent, mounted before any
    workspace is selected; `set_workspace()` (re)points it at one."""

    can_focus = True

    class SummaryUpdated(Message):
        """Posted whenever refresh_summary() recomputes — UtilityRail's
        problems badge subscribes (via MainScreen) so it can never
        disagree with what's actually shown here."""

        def __init__(
            self,
            count: int,
            age: str,
            reflection: str,
            *,
            problems_count: int | None = None,
            tooltip: str = "",
        ) -> None:
            self.count = count
            self.age = age
            self.reflection = reflection
            self.problems_count = count if problems_count is None else problems_count
            self.tooltip = tooltip
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.workspace_root: Path | None = None
        self.session: str | None = None
        self.projects: list | None = None
        self._dirty_count = 0
        self._dirty_checked_at = 0.0
        # Last painted chrome — watchfiles can fire bursts; skip Textual
        # updates when the visible summary is unchanged.
        self._painted: tuple | None = None

    def compose(self) -> ComposeResult:
        yield Static("ASSERTIONS", classes="activity-heading")
        yield Static(SUBTITLE, id="activity-subtitle")
        with Horizontal(id="activity-actions"):
            yield Button(
                "Review", id="activity-review-btn",
                tooltip="Open pending assertions in a tmux pane (live label: review)",
            )
            # Pause/Turn-off tooltips are state-dependent (e.g. explaining
            # *why* Pause is greyed out) — set in _refresh_automation_buttons
            # instead of a static value here that on_mount would immediately
            # overwrite anyway.
            yield Button("Pause", id="activity-pause-btn")
            yield Button("Turn off", id="activity-enabled-btn")
        yield Static(PLACEHOLDER, id="activity-body")

    def on_mount(self) -> None:
        # Automation state is global (not per-workspace), so the pause/
        # on-off buttons have something correct to show even before a
        # workspace is picked (unlike Review, which needs self.session).
        self._refresh_automation_buttons()
        # "reflection" and "pending" are terms this box uses without ever
        # defining — the subtitle above explains "assertions" but not the
        # background process that produces them. One tooltip on the whole
        # body covers both rather than inventing separate display wording
        # that would diverge from context_inbox.py's shared "reflection:"
        # prefix (also used by orcan doctor — renaming that string would
        # touch a wider, tested contract for a cockpit-only wording tweak).
        self.query_one("#activity-body", Static).tooltip = (
            "pending = facts proposed but not yet reviewed\n"
            "reflection = the background scan that reads session transcripts "
            "and proposes them\n"
            "automation = the on/off switch for that background scan "
            "(Pause/Turn off buttons above)"
        )

    def set_workspace(
        self,
        workspace_root: str,
        session: str,
        *,
        projects: list | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root)
        self.session = session
        self.projects = projects
        self._painted = None  # force paint for the new workspace
        self.refresh_summary()
        # exclusive=True cancels any previous run of this same worker (the
        # prior workspace's watch loop) before starting the new one.
        self.run_worker(self._watch_loop(), exclusive=True, group="watch")

    def _automation_paint(self) -> tuple:
        sync_automation_to_claude_availability()
        state = automation_state()
        has_claude = claude_on_path()
        pause_label = "Resume" if state["paused"] else "Pause"
        pause_disabled = (not state["enabled"]) or (not has_claude)
        if not has_claude:
            pause_tooltip = (
                "Assertions automation needs Claude Code on PATH "
                "(auto-propose/recap). Review still works for pending notes."
            )
        elif not state["enabled"]:
            pause_tooltip = "Automation is off — turn it on first to pause/resume it"
        elif state["paused"]:
            pause_tooltip = "Resume automation — go back to proposing new context assertions"
        else:
            pause_tooltip = "Pause automation — temporarily stop proposing new context assertions"

        enabled_label = "Turn on" if not state["enabled"] else "Turn off"
        enabled_disabled = not has_claude
        if not has_claude:
            enabled_tooltip = (
                "Install Claude Code in the container to enable assertions automation"
            )
        elif not state["enabled"]:
            enabled_tooltip = "Turn automation on — resume scanning sessions for new assertions"
        else:
            enabled_tooltip = "Turn automation off — stop scanning sessions for new assertions"
        return (
            pause_label,
            pause_disabled,
            pause_tooltip,
            enabled_label,
            enabled_disabled,
            enabled_tooltip,
        )

    def _apply_automation_paint(self, paint: tuple) -> None:
        (
            pause_label,
            pause_disabled,
            pause_tooltip,
            enabled_label,
            enabled_disabled,
            enabled_tooltip,
        ) = paint
        pause_btn = self.query_one("#activity-pause-btn", Button)
        pause_btn.label = pause_label
        pause_btn.disabled = pause_disabled
        pause_btn.tooltip = pause_tooltip
        enabled_btn = self.query_one("#activity-enabled-btn", Button)
        enabled_btn.label = enabled_label
        enabled_btn.disabled = enabled_disabled
        enabled_btn.tooltip = enabled_tooltip

    def _refresh_automation_buttons(self) -> None:
        self._apply_automation_paint(self._automation_paint())

    def refresh_summary(self) -> None:
        auto = self._automation_paint()
        if self.workspace_root is None:
            self._apply_automation_paint(auto)
            return
        summary = pending_summary(self.workspace_root)
        age = format_pending_age(summary["oldest_mtime"])
        reflection = reflection_status(self.workspace_root)
        count = summary["count"]
        # Dirty git is throttled — full status on every watchfiles tick is too
        # expensive for a badge. Re-scan at most every 30s.
        now = time.time()
        include_dirty = (now - self._dirty_checked_at) >= 30.0
        problems = problems_summary(
            self.workspace_root,
            projects=self.projects,
            include_dirty=include_dirty,
        )
        if include_dirty:
            self._dirty_count = int(problems["dirty"])
            self._dirty_checked_at = now
        else:
            problems = dict(problems)
            problems["dirty"] = self._dirty_count
            if self._dirty_count and "dirty" not in " ".join(problems["parts"]):
                problems["parts"] = list(problems["parts"]) + [f"{self._dirty_count} dirty"]
                problems["count"] = int(problems["pending"]) + int(problems["reflection_errors"]) + self._dirty_count
                problems["tooltip"] = " · ".join(problems["parts"]) if problems["parts"] else problems["tooltip"]

        # Cross-workspace pending (cheap — config roots only, no tmux live
        # probes; list_workspace_rows would re-check every session here).
        global_pending = count
        try:
            from orcan_cockpit.picker import workspace_roots

            global_pending = pending_across_roots(workspace_roots())
        except Exception:
            pass

        review_label = f"Review ([#fbbf24]{count}[/])" if count else "Review"
        review_disabled = self.session is None
        lines = [
            f"{count} pending" + (f" (oldest {age})" if age else ""),
            reflection,
            last_batch_feedback(self.workspace_root),
            *automation_status_lines(),
        ]
        if problems["parts"] and (
            problems["reflection_errors"] or problems["dirty"]
        ):
            lines.append("problems: " + " · ".join(problems["parts"]))
        if global_pending > count:
            lines.append(f"all workspaces: {global_pending} pending")

        agents = list_agent_panes(self.session) if self.session else []
        pinned = read_pinned_pane(self.workspace_root)
        if agents:
            bits = []
            for pane in agents:
                mark = "★" if pinned and pane["id"] == pinned else "·"
                bits.append(f"{mark}{pane['cmd']}")
            lines.append("agents: " + " ".join(bits))

        timeline = format_timeline(recent_decisions(self.workspace_root, limit=3))
        if timeline:
            lines.append("recent:")
            lines.extend(f"  {row}" for row in timeline)

        lines.extend(
            [
                "",
                r"Buttons above, or \[r] review · \[p] pause · \[o] on/off",
                f'[link="{DOCS_URL}"]Learn more →[/link]',
            ]
        )
        body = "\n".join(lines)
        tooltip = problems["tooltip"]
        if global_pending > count:
            tooltip = f"{tooltip} · {global_pending} pending across workspaces"
        badge = max(int(problems["count"]), int(global_pending))
        painted = (auto, review_label, review_disabled, body, count, age, reflection, badge, tooltip)
        if painted == self._painted:
            return
        self._painted = painted
        self._apply_automation_paint(auto)
        review_btn = self.query_one("#activity-review-btn", Button)
        review_btn.label = review_label
        review_btn.disabled = review_disabled
        self.query_one("#activity-body", Static).update(body)
        self.post_message(
            self.SummaryUpdated(
                count,
                age,
                reflection,
                problems_count=badge,
                tooltip=tooltip,
            )
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "activity-review-btn" and self.session is not None:
            run_context_review_popup(self.session)
            event.stop()
        elif event.button.id == "activity-pause-btn":
            toggle_automation_pause()
            self.refresh_summary()
            event.stop()
        elif event.button.id == "activity-enabled-btn":
            toggle_automation_enabled()
            self.refresh_summary()
            event.stop()

    def on_key(self, event: events.Key) -> None:
        if event.key == "r" and self.session is not None:
            run_context_review_popup(self.session)
            event.stop()
        elif event.key == "p":
            toggle_automation_pause()
            self.refresh_summary()
            event.stop()
        elif event.key == "o":
            toggle_automation_enabled()
            self.refresh_summary()
            event.stop()

    async def _watch_loop(self) -> None:
        if awatch is None or self.workspace_root is None:
            return
        watch_dir = self.workspace_root / ".orcan"
        watch_dir.mkdir(parents=True, exist_ok=True)
        # Also watch automation.json (history bind) when present.
        roots = [watch_dir]
        try:
            from orcan.automation import automation_dir

            auto_dir = automation_dir()
            auto_dir.mkdir(parents=True, exist_ok=True)
            roots.append(auto_dir)
        except ImportError:
            pass
        async for _changes in awatch(*roots):
            self.refresh_summary()
