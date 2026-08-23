"""Agent task handoff — filesystem queue with atomic claim.

discussion/planning agent -> structured task manifest -> Orcan inbox ->
execution agent: the discussion agent never hands the executor its full
transcript, only this manifest (see AGENTS.md "Agent handoff").

Lifecycle mirrors the existing Context Assertions propose -> review ->
accept pattern (context_assertions.py) rather than inventing a new shape:
propose (draft/approve/auto policy) -> [human approve, unless auto] ->
inbox -> claim (atomic) -> processing -> done|review|failed.

JSON, not YAML — same reason as orcan.config.json (stdlib only, no PyYAML).
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

STATES = ("proposals", "inbox", "processing", "review", "done", "failed")
DEFAULT_POLICY = "approve"


def _tasks_root(workspace_root: Path) -> Path:
    return Path(workspace_root) / ".orcan" / "tasks"


def _state_dir(workspace_root: Path, state: str, *, ensure: bool = False) -> Path:
    if state not in STATES:
        raise ValueError(f"unknown task state: {state}")
    d = _tasks_root(workspace_root) / state
    if ensure:
        d.mkdir(parents=True, exist_ok=True)
    return d


def new_task_id() -> str:
    return f"task-{uuid.uuid4().hex[:12]}"


def propose(workspace_root: Path, task: dict[str, Any], *, policy: str | None = None) -> Path:
    """Write a structured task manifest. Returns its path.

    policy (falls back to task["execution"]["policy"], then DEFAULT_POLICY):
      draft   -> stays in proposals/ only — nothing ever picks it up automatically.
      approve -> proposals/, needs an explicit approve() before it's claimable.
      auto    -> written straight to inbox/, claimable immediately.
    Default is "approve" — safe until a workspace/task explicitly opts into auto.
    """
    task = dict(task)
    task.setdefault("id", new_task_id())
    execution = dict(task.get("execution") or {})
    resolved_policy = policy or execution.get("policy") or DEFAULT_POLICY
    if resolved_policy not in ("draft", "approve", "auto"):
        raise ValueError(f"unknown execution policy: {resolved_policy}")
    execution["policy"] = resolved_policy
    task["execution"] = execution
    task["status"] = "approved" if resolved_policy == "auto" else "proposed"
    task.setdefault("created_at", time.time())

    dest_state = "inbox" if resolved_policy == "auto" else "proposals"
    dest_dir = _state_dir(workspace_root, dest_state, ensure=True)
    path = dest_dir / f"{task['id']}.json"
    path.write_text(json.dumps(task, indent=2) + "\n", encoding="utf-8")
    return path


def approve(workspace_root: Path, task_id: str) -> Path:
    """Move a proposed task from proposals/ to inbox/ — the human approval gate.

    Refuses a task whose policy is "draft": that policy means "don't even
    offer this for execution", the same hard boundary the Reflection Stop
    hook has around accept/reject/retire in context_assertions.py.
    """
    src = _state_dir(workspace_root, "proposals") / f"{task_id}.json"
    if not src.is_file():
        raise FileNotFoundError(f"no proposed task: {task_id}")
    task = json.loads(src.read_text(encoding="utf-8"))
    if (task.get("execution") or {}).get("policy") == "draft":
        raise ValueError(f"task {task_id} has policy=draft — cannot be approved for execution")
    task["status"] = "approved"
    task["approved_at"] = time.time()
    dest_dir = _state_dir(workspace_root, "inbox", ensure=True)
    dest = dest_dir / f"{task_id}.json"
    dest.write_text(json.dumps(task, indent=2) + "\n", encoding="utf-8")
    src.unlink()
    return dest


def claim(workspace_root: Path, task_id: str, claimant: str) -> dict[str, Any] | None:
    """Atomically move inbox/<id>.json -> processing/<id>.json.

    Returns the claimed task, or None if another worker already claimed it
    first. Safe under concurrent claimers: os.rename on one source path can
    only ever succeed once — the loser gets an OSError, never a partial or
    duplicated move (this is what makes claim() race-safe without a lock).
    """
    src = _state_dir(workspace_root, "inbox") / f"{task_id}.json"
    dest_dir = _state_dir(workspace_root, "processing", ensure=True)
    dest = dest_dir / f"{task_id}.json"
    try:
        src.rename(dest)
    except OSError:
        return None
    task = json.loads(dest.read_text(encoding="utf-8"))
    task["status"] = "processing"
    task["claimed_by"] = claimant
    task["claimed_at"] = time.time()
    dest.write_text(json.dumps(task, indent=2) + "\n", encoding="utf-8")
    return task


def claim_next(workspace_root: Path, claimant: str) -> dict[str, Any] | None:
    """Claim the oldest task currently in inbox/, if any."""
    inbox_dir = _state_dir(workspace_root, "inbox")
    if not inbox_dir.is_dir():
        return None
    candidates = sorted(inbox_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    for path in candidates:
        claimed = claim(workspace_root, path.stem, claimant)
        if claimed is not None:
            return claimed
    return None


def complete(
    workspace_root: Path, task_id: str, *, outcome: str, result: dict[str, Any] | None = None
) -> Path:
    """Move processing/<id>.json -> done|review|failed/<id>.json with the result attached."""
    if outcome not in ("done", "review", "failed"):
        raise ValueError(f"unknown outcome: {outcome}")
    src = _state_dir(workspace_root, "processing") / f"{task_id}.json"
    if not src.is_file():
        raise FileNotFoundError(f"no processing task: {task_id}")
    task = json.loads(src.read_text(encoding="utf-8"))
    task["status"] = outcome
    task["completed_at"] = time.time()
    if result is not None:
        task["result"] = result
    dest_dir = _state_dir(workspace_root, outcome, ensure=True)
    dest = dest_dir / f"{task_id}.json"
    dest.write_text(json.dumps(task, indent=2) + "\n", encoding="utf-8")
    src.unlink()
    return dest


def list_tasks(workspace_root: Path, state: str) -> list[dict[str, Any]]:
    d = _state_dir(workspace_root, state)
    if not d.is_dir():
        return []
    tasks: list[dict[str, Any]] = []
    for path in sorted(d.glob("*.json")):
        try:
            tasks.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return tasks
