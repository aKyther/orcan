"""AgentExecutor abstraction — the inbox is Orcan's protocol, the agent is a worker.

execute(task, context) -> ExecutionResult. Orcan resolves workspace/context
and claims the task; the executor only ever runs one already-claimed task
against a resolved cwd — it does not know about the inbox, claiming, or
approval policy. Not every executor is implemented (only what's currently
needed); the point is the boundary, not a full product matrix.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orcan.agent_inbox import claim_next, complete  # noqa: E402


@dataclass
class ExecutionResult:
    ok: bool
    output: str
    returncode: int | None = None
    duration_s: float = 0.0


class AgentExecutor:
    def execute(self, task: dict[str, Any], context: dict[str, Any]) -> ExecutionResult:
        raise NotImplementedError


class ShellExecutor(AgentExecutor):
    """Runs task["execution"]["command"] as a shell command in context["cwd"].

    For tests/CI and simple automation tasks — not a substitute for an
    actual coding agent.
    """

    def execute(self, task: dict[str, Any], context: dict[str, Any]) -> ExecutionResult:
        command = (task.get("execution") or {}).get("command")
        if not command:
            return ExecutionResult(ok=False, output="task has no execution.command")
        cwd = context.get("cwd") or "."
        started = time.monotonic()
        proc = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True)
        return ExecutionResult(
            ok=proc.returncode == 0,
            output=proc.stdout + proc.stderr,
            returncode=proc.returncode,
            duration_s=time.monotonic() - started,
        )


def build_prompt(task: dict[str, Any]) -> str:
    """Structured task manifest -> one prompt string.

    The discussion agent hands the executor this, never its own transcript —
    see agent_inbox.py's module docstring.
    """
    lines = [f"# {task.get('title') or task.get('id') or 'task'}", ""]
    if task.get("goal"):
        lines += ["## Goal", str(task["goal"]), ""]
    if task.get("context"):
        lines += ["## Context", str(task["context"]), ""]
    if task.get("decisions"):
        lines += ["## Decisions already made", *[f"- {d}" for d in task["decisions"]], ""]
    if task.get("constraints"):
        lines += ["## Constraints", *[f"- {c}" for c in task["constraints"]], ""]
    if task.get("files"):
        lines += ["## Relevant files", *[f"- {f}" for f in task["files"]], ""]
    if task.get("acceptance"):
        lines += ["## Acceptance criteria", *[f"- {a}" for a in task["acceptance"]], ""]
    if task.get("risks"):
        lines += ["## Known risks", *[f"- {r}" for r in task["risks"]], ""]
    return "\n".join(lines).strip() + "\n"


class ClaudeExecutor(AgentExecutor):
    """Invokes `claude -p <prompt>` non-interactively in context["cwd"]."""

    def __init__(self, claude_bin: str = "claude"):
        self.claude_bin = claude_bin

    def execute(self, task: dict[str, Any], context: dict[str, Any]) -> ExecutionResult:
        prompt = build_prompt(task)
        cwd = context.get("cwd") or "."
        started = time.monotonic()
        proc = subprocess.run(
            [self.claude_bin, "-p", prompt], cwd=cwd, capture_output=True, text=True
        )
        return ExecutionResult(
            ok=proc.returncode == 0,
            output=proc.stdout + proc.stderr,
            returncode=proc.returncode,
            duration_s=time.monotonic() - started,
        )


class CodexExecutor(AgentExecutor):
    """Invokes `codex exec <prompt>` non-interactively in context["cwd"]."""

    def __init__(self, codex_bin: str = "codex"):
        self.codex_bin = codex_bin

    def execute(self, task: dict[str, Any], context: dict[str, Any]) -> ExecutionResult:
        prompt = build_prompt(task)
        cwd = context.get("cwd") or "."
        started = time.monotonic()
        proc = subprocess.run(
            [self.codex_bin, "exec", prompt], cwd=cwd, capture_output=True, text=True
        )
        return ExecutionResult(
            ok=proc.returncode == 0,
            output=proc.stdout + proc.stderr,
            returncode=proc.returncode,
            duration_s=time.monotonic() - started,
        )


def dispatch_once(
    workspace_root: Path, executor: AgentExecutor, claimant: str
) -> dict[str, Any] | None:
    """Claim one task from inbox/ and run it through `executor`.

    Returns the completed task dict (with `result` attached), or None if
    nothing was in inbox/ to claim. This is the body of the watch loop —
    watch_forever (thin CLI wrapper) just calls this on an interval;
    interactive sessions don't need to poll the inbox themselves.
    """
    task = claim_next(workspace_root, claimant)
    if task is None:
        return None
    result = executor.execute(task, {"cwd": str(workspace_root)})
    outcome = "done" if result.ok else "failed"
    completed_path = complete(
        workspace_root,
        task["id"],
        outcome=outcome,
        result={
            "output": result.output,
            "returncode": result.returncode,
            "duration_s": result.duration_s,
        },
    )
    return {**task, "status": outcome, "_completed_path": str(completed_path)}
