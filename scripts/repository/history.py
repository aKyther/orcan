#!/usr/bin/env python3
"""Usage history: recent projects / workspaces / worktrees / work items.

Same upsert-by-key JSON idiom as the worktree registry
(git_worktrees.py's registry.json) — one small file, no database. Reuses
context_assertions.project_id() (git-common-dir based, worktree-stable) as
the canonical project identity instead of inventing a parallel one, per
the existing pattern: canonical project identity is more stable than a
workspace or worktree name.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from context_assertions import project_id  # noqa: E402

DEFAULT_FILENAME = "history.json"


def store_path(orcan_data: Path) -> Path:
    return Path(orcan_data) / "state" / DEFAULT_FILENAME


def load(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def save(path: Path, entries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def _key(entry: dict[str, Any]) -> tuple:
    return (
        entry.get("project_id"),
        entry.get("workspace"),
        entry.get("worktree"),
        entry.get("work_item"),
    )


def record_use(
    path: Path,
    *,
    workspace: str,
    project_path: Path | None = None,
    worktree: str | None = None,
    work_item: str | None = None,
    now: float | None = None,
) -> list[dict[str, Any]]:
    """Upsert one usage row (bump usage_count / last_used) and persist it.

    Identity for dedup is (project_id, workspace, worktree, work_item) —
    the same physical project can appear under several rows if used from
    different workspaces/worktrees, which is intentional: history tracks
    project -> workspace -> worktree -> work_item chains (see docstring),
    not just a flat "recent projects" list.
    """
    entries = load(path)
    pid = project_id(project_path) if project_path is not None else None
    row_key = (pid, workspace, worktree, work_item)
    when = now if now is not None else time.time()

    for entry in entries:
        if _key(entry) == row_key:
            entry["last_used"] = when
            entry["usage_count"] = int(entry.get("usage_count", 0)) + 1
            save(path, entries)
            return entries

    entries.append(
        {
            "project_id": pid,
            "workspace": workspace,
            "worktree": worktree,
            "work_item": work_item,
            "last_used": when,
            "usage_count": 1,
        }
    )
    save(path, entries)
    return entries


def recent(
    path: Path, *, limit: int = 10, workspace: str | None = None
) -> list[dict[str, Any]]:
    """Most-recently-used rows, newest first. Optionally filtered to one workspace."""
    entries = load(path)
    if workspace is not None:
        entries = [e for e in entries if e.get("workspace") == workspace]
    entries.sort(key=lambda e: e.get("last_used", 0), reverse=True)
    return entries[:limit]


def _format_row(entry: dict[str, Any]) -> str:
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(entry.get("last_used", 0)))
    bits = [entry.get("workspace") or "?"]
    if entry.get("worktree"):
        bits.append(f"worktree={entry['worktree']}")
    if entry.get("work_item"):
        bits.append(f"work_item={entry['work_item']}")
    count = entry.get("usage_count", 1)
    return f"{when}  {' '.join(bits)}  (used {count}x)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, help="ORCAN_DATA root")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_record = sub.add_parser("record", help="Record one workspace-entered event")
    p_record.add_argument("--workspace", required=True)
    p_record.add_argument("--project-path", default="")
    p_record.add_argument("--worktree", default="")
    p_record.add_argument("--work-item", default="")

    p_recent = sub.add_parser("recent", help="List most-recently-used rows")
    p_recent.add_argument("--limit", type=int, default=10)
    p_recent.add_argument("--workspace", default="")

    args = parser.parse_args()
    path = store_path(Path(args.data))

    if args.cmd == "record":
        record_use(
            path,
            workspace=args.workspace,
            project_path=Path(args.project_path) if args.project_path else None,
            worktree=args.worktree or None,
            work_item=args.work_item or None,
        )
        return 0

    if args.cmd == "recent":
        rows = recent(path, limit=args.limit, workspace=args.workspace or None)
        if not rows:
            print("(no history yet)")
            return 0
        for entry in rows:
            print(_format_row(entry))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
