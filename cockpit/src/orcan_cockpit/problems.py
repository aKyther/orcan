"""Aggregated "Problems" signal for the cockpit rail (IDE-style badge).

Stdlib-only (+ vendored context_inbox) so host tests can lock counts without
Textual. Combines pending assertions, reflection failures, and dirty linked
checkouts into one attention count — not a second dashboard.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

for _lib in (
    Path("/usr/local/lib"),
    Path(__file__).resolve().parents[3] / "docker" / "rootfs" / "usr" / "local" / "lib",
):
    if (_lib / "orcan" / "context_inbox.py").is_file():
        sys.path.insert(0, str(_lib))
        break

from orcan.context_inbox import pending_summary, reflection_status  # noqa: E402


def reflection_error_count(workspace_root: Path) -> int:
    """How many reflection-state sessions currently record ``last_error``."""
    state_path = workspace_root / ".orcan" / "reflection-state.json"
    if not state_path.is_file():
        return 0
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(state, dict):
        return 0
    return sum(
        1
        for entry in state.values()
        if isinstance(entry, dict) and entry.get("last_error")
    )


def dirty_project_count(projects: list[Any] | None, *, limit: int = 8) -> int:
    """Cheap ``git status --porcelain`` count across project paths (capped)."""
    dirty = 0
    for project in (projects or [])[:limit]:
        if not isinstance(project, dict):
            continue
        path = str(project.get("path") or "").strip()
        if not path or not (Path(path) / ".git").exists():
            continue
        try:
            result = subprocess.run(
                ["git", "-C", path, "status", "--porcelain", "-uno"],
                capture_output=True,
                text=True,
                timeout=0.4,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and result.stdout.strip():
            dirty += 1
    return dirty


def problems_summary(
    workspace_root: str | Path | None,
    *,
    projects: list[Any] | None = None,
    include_dirty: bool = False,
) -> dict[str, Any]:
    """Return ``{count, pending, reflection_errors, dirty, parts, tooltip}``.

    *include_dirty* defaults False — ``git status`` is relatively expensive;
    callers should pass True on a throttle (e.g. every 30s) or expand.
    """
    root = Path(workspace_root) if workspace_root else None
    pending = 0
    refl_err = 0
    dirty = 0
    parts: list[str] = []

    if root is not None and root.is_dir():
        pending = int(pending_summary(root).get("count") or 0)
        refl_err = reflection_error_count(root)
        if include_dirty:
            dirty = dirty_project_count(projects)
        _ = reflection_status(root)

    if pending:
        parts.append(f"{pending} pending")
    if refl_err:
        parts.append(f"{refl_err} reflect err")
    if dirty:
        parts.append(f"{dirty} dirty")

    count = pending + refl_err + dirty
    tooltip = " · ".join(parts) if parts else "No pending problems"
    return {
        "count": count,
        "pending": pending,
        "reflection_errors": refl_err,
        "dirty": dirty,
        "parts": parts,
        "tooltip": tooltip,
    }


def pending_across_roots(roots: list[Path] | None) -> int:
    """Sum pending counts across workspace roots (no dirty/git)."""
    total = 0
    for root in roots or []:
        if root.is_dir():
            total += int(pending_summary(root).get("count") or 0)
    return total
