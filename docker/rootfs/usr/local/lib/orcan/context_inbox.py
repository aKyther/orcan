"""Pending-Context-Assertions helpers, shared by `orcan-context-review` and
the cockpit's side panel (`orcan.cockpit.panel`).

Stdlib-only and framework-free by design (no Textual/pyte here) so it stays
directly unit-testable on the host, same convention as
`scripts/repository/context_tui.py`'s pure/curses-free functions.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def load_inbox_candidates(workspace_root: Path) -> list[dict[str, Any]]:
    """Undecided, non-flag drops sitting in .orcan/context-inbox/ right now —
    reviewable without a prior `orcan sync`, since a propose drop already
    carries its full content. Sorted oldest to newest by file mtime. Each
    item carries _source="inbox" and _drop_path so review_candidates() knows
    to rewrite the drop in place (mirroring what interactive
    orcan-context-propose already does) instead of writing a
    .orcan/context-decisions/ file."""
    inbox = workspace_root / ".orcan" / "context-inbox"
    if not inbox.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for drop in inbox.glob("*.json"):
        try:
            payload = json.loads(drop.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if str(payload.get("flag_existing_id") or "").strip():
            continue  # reconsider-style drop — no displayable content here
        if payload.get("decision"):
            continue  # already decided in a prior review run, awaiting sync
        items.append(
            {
                "id": drop.stem,
                "project_name": payload.get("project_name"),
                "title": payload.get("title"),
                "content": payload.get("content"),
                "justification": payload.get("justification"),
                "applicability": payload.get("applicability") or {},
                "epistemic_status": payload.get("epistemic_status") or "fact",
                "criticality": payload.get("criticality") or "normal",
                "relations": payload.get("relations") or [],
                "_source": "inbox",
                "_drop_path": drop,
            }
        )
    items.sort(key=lambda it: it["_drop_path"].stat().st_mtime)
    return items


def pending_summary(workspace_root: Path) -> dict[str, Any]:
    """Count + oldest-item age across every pending source `orcan-context-review`
    would show a human: fresh inbox drops, plus the host-generated review
    queue's "candidates" and "reconsider" entries. A glance-level condensation
    of the same data, for the cockpit side panel."""
    count = 0
    oldest_mtime: float | None = None

    for item in load_inbox_candidates(workspace_root):
        count += 1
        mtime = item["_drop_path"].stat().st_mtime
        if oldest_mtime is None or mtime < oldest_mtime:
            oldest_mtime = mtime

    queue_path = workspace_root / ".orcan" / "context-review-queue.json"
    if queue_path.is_file():
        try:
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            queue = {}
        extra = len(queue.get("candidates") or []) + len(queue.get("reconsider") or [])
        if extra:
            count += extra
            mtime = queue_path.stat().st_mtime
            if oldest_mtime is None or mtime < oldest_mtime:
                oldest_mtime = mtime

    return {"count": count, "oldest_mtime": oldest_mtime}


def format_pending_age(oldest_mtime: float | None, *, now: float | None = None) -> str:
    """'3h', '2d', '' (nothing pending) — condensed age for a status line."""
    if oldest_mtime is None:
        return ""
    age_s = max(0, int((now if now is not None else time.time()) - oldest_mtime))
    if age_s < 3600:
        return f"{age_s // 60}m"
    if age_s < 86400:
        return f"{age_s // 3600}h"
    return f"{age_s // 86400}d"


def reflection_status(workspace_root: Path) -> str:
    """One-line summary of `.orcan/reflection-state.json` — surfaces a stuck
    reflection hook the same way `orcan doctor` does, at a glance."""
    state_path = workspace_root / ".orcan" / "reflection-state.json"
    if not state_path.is_file():
        return "reflection: (no sessions yet)"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "reflection: (state unreadable)"
    if not isinstance(state, dict):
        return "reflection: (state unreadable)"
    errors = [
        s.get("last_error")
        for s in state.values()
        if isinstance(s, dict) and s.get("last_error")
    ]
    if errors:
        return f"reflection: ⚠ last call failed ({str(errors[-1])[:60]})"
    return "reflection: ok"
