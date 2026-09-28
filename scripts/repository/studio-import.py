#!/usr/bin/env python3
"""Read-only import plan for Orcan Studio."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse


def suggested_name(source: str) -> str:
    candidate = Path(urlparse(source).path).name or Path(source).name
    return candidate.removesuffix(".git") or "repository"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--projects-root", required=True)
    parser.add_argument("--destination")
    args = parser.parse_args()
    root = Path(args.projects_root).expanduser().resolve()
    destination = Path(args.destination).expanduser() if args.destination else root / suggested_name(args.source)
    destination = destination.resolve()
    exists = destination.exists()
    git = (destination / ".git").exists() if exists and destination.is_dir() else False
    blockers = []
    if exists and not git:
        blockers.append("destination exists but is not a Git repository")
    print(json.dumps({"ok": True, "plan": {"operation": "repository_import", "source": args.source,
        "projects_root": str(root), "destination": str(destination), "default_destination": args.destination is None,
        "destination_state": "git_repository" if git else "missing" if not exists else "directory",
        "changes": [f"clone or attach repository at {destination}"], "blockers": blockers,
        "ready": not blockers}}, separators=(",", ":")))


if __name__ == "__main__":
    main()
