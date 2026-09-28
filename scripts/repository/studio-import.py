#!/usr/bin/env python3
"""Read-only import plan for Orcan Studio."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from urllib.parse import urlparse


def suggested_name(source: str) -> str:
    candidate = Path(urlparse(source).path).name or Path(source).name
    return candidate.removesuffix(".git") or "repository"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "apply"))
    parser.add_argument("--source", required=True)
    parser.add_argument("--projects-root", required=True)
    parser.add_argument("--destination")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    root = Path(args.projects_root).expanduser().resolve()
    destination = (
        Path(args.destination).expanduser()
        if args.destination
        else root / suggested_name(args.source)
    )
    destination = destination.resolve()
    exists = destination.exists()
    git = (destination / ".git").exists() if exists and destination.is_dir() else False
    blockers = []
    if exists and not git:
        blockers.append("destination exists but is not a Git repository")
    plan = {
        "operation": "repository_import",
        "source": args.source,
        "projects_root": str(root),
        "destination": str(destination),
        "default_destination": args.destination is None,
        "destination_state": "git_repository"
        if git
        else "missing"
        if not exists
        else "directory",
        "changes": [f"clone or attach repository at {destination}"],
        "blockers": blockers,
        "ready": not blockers,
    }
    if args.mode == "plan":
        print(json.dumps({"ok": True, "plan": plan}, separators=(",", ":")))
        return
    if not args.yes or not plan["ready"] or exists:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "apply requires --yes and a missing, ready destination",
                }
            )
        )
        raise SystemExit(2)
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "clone", "--", args.source, str(destination)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        print(
            json.dumps(
                {"ok": False, "error": result.stderr.strip() or "git clone failed"}
            )
        )
        raise SystemExit(result.returncode)
    print(
        json.dumps(
            {
                "ok": True,
                "result": {"destination": str(destination), "operation": "git clone"},
            },
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
