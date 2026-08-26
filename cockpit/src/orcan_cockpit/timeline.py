"""Recent assertion decisions timeline (IDE Local History vibe).

Stdlib-only — reads ``.orcan/context-decisions/`` and decided inbox drops.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def recent_decisions(workspace_root: Path, *, limit: int = 5) -> list[dict[str, Any]]:
    """Newest-first ``{when, decision, title, project}`` rows."""
    rows: list[tuple[float, dict[str, Any]]] = []
    decisions = workspace_root / ".orcan" / "context-decisions"
    if decisions.is_dir():
        for drop in decisions.glob("*.json"):
            try:
                payload = json.loads(drop.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            rows.append(
                (
                    _mtime(drop),
                    {
                        "decision": str(payload.get("decision") or "?"),
                        "title": str(payload.get("id") or drop.stem),
                        "project": str(payload.get("project_name") or ""),
                    },
                )
            )

    inbox = workspace_root / ".orcan" / "context-inbox"
    if inbox.is_dir():
        for drop in inbox.glob("*.json"):
            try:
                payload = json.loads(drop.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict) or not payload.get("decision"):
                continue
            rows.append(
                (
                    _mtime(drop),
                    {
                        "decision": str(payload.get("decision") or "?"),
                        "title": str(payload.get("title") or drop.stem),
                        "project": str(payload.get("project_name") or ""),
                    },
                )
            )

    rows.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in rows[:limit]]


def format_timeline(rows: list[dict[str, Any]]) -> list[str]:
    """One short line per decision for glance / activity."""
    lines: list[str] = []
    for row in rows:
        dec = row.get("decision") or "?"
        title = (row.get("title") or "")[:40]
        project = row.get("project") or ""
        prefix = f"[{project}] " if project else ""
        lines.append(f"{dec}: {prefix}{title}")
    return lines
