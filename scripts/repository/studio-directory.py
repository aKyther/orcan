#!/usr/bin/env python3
"""Plan and create a named directory inside Orcan's managed projects root."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def valid_name(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", value))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "apply"))
    parser.add_argument("--projects-root", required=True)
    parser.add_argument("--parent", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    root = Path(args.projects_root).expanduser().resolve()
    parent = Path(args.parent).expanduser().resolve()
    blockers: list[str] = []
    try:
        parent.relative_to(root)
    except ValueError:
        blockers.append("selected parent is outside Orcan's managed projects root")
    if not parent.is_dir():
        blockers.append("selected parent directory does not exist")
    if not valid_name(args.name):
        blockers.append("folder name must be a single name, not a path")
    destination = (parent / args.name).resolve()
    if destination.exists():
        blockers.append("folder already exists")
    plan = {
        "operation": "directory_create",
        "parent": str(parent),
        "destination": str(destination),
        "changes": [f"create managed folder {destination}"],
        "blockers": blockers,
        "ready": not blockers,
    }
    if args.mode == "plan":
        print(json.dumps({"ok": True, "plan": plan}, separators=(",", ":")))
        return
    if not args.yes or not plan["ready"]:
        print(
            json.dumps({"ok": False, "error": "apply requires --yes and a ready plan"})
        )
        raise SystemExit(2)
    destination.mkdir()
    print(
        json.dumps(
            {
                "ok": True,
                "result": {"operation": "directory_create", "path": str(destination)},
            },
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
