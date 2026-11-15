"""On-demand executor overview; the executor owns its database and processes."""

from __future__ import annotations

import asyncio
import json
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Button, Static

from orcan_cockpit.attention import attention_reason, matching_workspaces
from orcan_cockpit.sheet_modal import SHEET_CSS, SheetModal


async def read_executor(command: str) -> dict:
    process = await asyncio.create_subprocess_exec(
        "orcan-executor",
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async with asyncio.timeout(5):
            chunks = []
            size = 0
            while chunk := await process.stdout.read(8192):
                size += len(chunk)
                if size > 65536:
                    raise ValueError("Executor overview exceeded its size limit")
                chunks.append(chunk)
            output = b"".join(chunks)
            await process.wait()
        if process.returncode:
            raise ValueError("Executor overview unavailable; run orcan-executor doctor")
        value = json.loads(output)
        if not isinstance(value, dict):
            raise TypeError("Invalid executor overview")
        return value
    finally:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()


async def read_overview() -> dict:
    return await read_executor("overview")


async def read_pulse() -> dict:
    return await read_executor("pulse")


def attention_jobs(value: dict) -> list[dict]:
    if "attention" in value:
        return value["attention"]["jobs"]
    return [job for job in value.get("jobs", []) if attention_reason(job)]


def format_overview(value: dict) -> str:
    counts, settings = value.get("counts", {}), value.get("settings", {})
    lines = [
        "This Orcan instance · last 3 hours · latest 20 jobs",
        f"Queued: {counts.get('queued', 0)} · running: {counts.get('running', 0)} · passed: {counts.get('passed', 0)}",
        f"Parallel job cap: {settings.get('max_running', '?')} · queue cap: {settings.get('max_pending', '?')}",
    ]
    communication = value.get("communication", {})
    lines.append(
        f"Redis: {communication.get('redis_status') or 'no sample'} · "
        f"pending events: {communication.get('pending_events', 0)} · "
        f"interrupted candidates: {communication.get('interrupted_jobs', 0)}"
    )
    if communication.get("health_stale"):
        lines.append("Cached diagnostics are stale; run orcan-executor diagnostics")
    for lane, state in value.get("lanes", {}).items():
        status = (
            "ready"
            if state.get("ready")
            else "configured, unavailable"
            if state.get("configured")
            else "disabled"
        )
        lines.append(f"Queue {lane}: {status}")
    attention = attention_jobs(value)
    count = value.get("attention", {}).get("count", len(attention))
    lines.append(f"\nNEEDS ATTENTION · {count} outstanding · showing {len(attention)}")
    for job in attention:
        lines.append(f"{job['status']} · {job.get('task') or job['id'][:12]} · {job['id']}")
        lines.append(attention_reason(job))
    if "attention" not in value:
        lines.append("Attention is limited to recent jobs; update the executor for complete coverage.")
    if not attention:
        lines.append("No items requiring attention in the available data.")
    lines.append("\nRECENT JOBS")
    for job in value.get("jobs", []):
        lines.extend(
            [
                "",
                f"{job['status']} · {job['task'] or job['id'][:12]} · {job['profile']} · queue {job.get('lane') or 'unknown'}",
                f"{job['repo']} · {job['sha'][:12]}",
                f"Job: {job['id']}",
            ]
        )
        if job.get("admission_reason"):
            lines.append(
                "Waiting: "
                + {
                    "capacity": "parallel job limit",
                    "disk_space": "low disk space; inspect orcan-executor storage",
                    "fair_turn": "another repository's turn",
                }.get(job["admission_reason"], "admission")
            )
        if job.get("superseded_by"):
            lines.append("Superseded by job: " + job["superseded_by"])
        if job.get("progress"):
            step = job["progress"]
            lines.append(f"Step {step['index']}/{step['total']}: {step['status']}")
        if job.get("seconds") is not None:
            lines.append(f"Execution: {job['seconds']:.2f}s")
        if job.get("details_expired"):
            lines.append("Logs expired; compact history retained")
    if not value.get("jobs"):
        lines.append(
            "\nNo recent jobs. Use a committed project profile to submit work."
        )
    lines.append(
        "\nCLI: orcan-executor result JOB · cancel JOB (queued only)\nDashboard: host command orcan executor url · displaying this list does not acknowledge results."
    )
    return "\n".join(lines)


class JobsModal(SheetModal):
    REFRESH_SECONDS = 5
    CSS = SHEET_CSS + "#jobs-dialog {width: 90;} #jobs-body {padding: 1 0;} #jobs-targets {height: auto;}"
    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("escape", "dismiss_close", "Close"),
        ("r", "refresh", "Refresh"),
    ]

    def __init__(self, workspaces: list[dict] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.workspaces = workspaces or []
        self._targets: dict[str, dict] = {}
        self._refreshing = False
        self._last_text: str | None = None

    def compose(self) -> ComposeResult:
        with Container(classes="sheet", id="jobs-dialog"):
            with Horizontal(classes="sheet-header"):
                yield Static("ATTENTION & JOBS", classes="sheet-title")
                yield Button("Refresh", id="jobs-refresh", classes="sheet-close")
                yield Button("Close", id="jobs-close", classes="sheet-close")
            with VerticalScroll():
                yield Static("Loading…", id="jobs-body", markup=False)
                yield Container(id="jobs-targets")

    def on_mount(self) -> None:
        super().on_mount()
        self.action_refresh()
        self.set_interval(self.REFRESH_SECONDS, self.action_refresh)

    def action_refresh(self) -> None:
        if self._refreshing or not self.is_current:
            return
        self._refreshing = True
        self.run_worker(self.refresh_overview(), group="jobs", exclusive=True, exit_on_error=False)

    async def refresh_overview(self) -> None:
        try:
            targets = {}
            try:
                value = await read_overview()
                text = format_overview(value)
                sessions = set()
                for job in attention_jobs(value):
                    for row in matching_workspaces(job, self.workspaces):
                        if row["session"] in sessions:
                            continue
                        sessions.add(row["session"])
                        targets[f"jobs-workspace-{len(targets)}"] = row
            except (OSError, ValueError, TimeoutError, KeyError, TypeError):
                text = "Executor unavailable, disabled or image outdated. Run orcan-executor doctor.\nEnable from the host with orcan up --with-redis."
            if text == self._last_text and targets == self._targets:
                return
            scroll = self.query_one(VerticalScroll)
            offset = scroll.scroll_offset
            if targets != self._targets:
                container = self.query_one("#jobs-targets", Container)
                await container.remove_children()
                self._targets = targets
                for key, row in targets.items():
                    await container.mount(Button(f"Open workspace: {row['name']}", id=key))
            if text != self._last_text:
                self.query_one("#jobs-body", Static).update(text)
                self._last_text = text
            self.call_after_refresh(scroll.scroll_to, x=offset.x, y=offset.y, animate=False)
        finally:
            self._refreshing = False

    def action_dismiss_close(self) -> None:
        self.dismiss("close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id in self._targets:
            self.dismiss(self._targets[event.button.id])
        elif event.button.id == "jobs-close":
            self.action_dismiss_close()
        elif event.button.id == "jobs-refresh":
            self.action_refresh()
