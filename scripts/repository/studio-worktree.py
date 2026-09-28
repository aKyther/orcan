#!/usr/bin/env python3
"""Read-only worktree plan consumed by Orcan Studio."""
from __future__ import annotations
import argparse, json, subprocess
from pathlib import Path

def run(repo: Path, *args: str) -> str | None:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True); parser.add_argument("--branch", required=True)
    parser.add_argument("--worktrees-root", required=True); parser.add_argument("--workspace", action="append", default=[])
    args = parser.parse_args(); repo = Path(args.repo).resolve(); root = Path(args.worktrees_root).resolve()
    destination = root / repo.name / args.branch
    blockers = []
    if run(repo, "rev-parse", "--is-inside-work-tree") != "true": blockers.append("parent is not a Git repository")
    if destination.exists(): blockers.append("managed worktree destination already exists")
    print(json.dumps({"ok": True, "plan": {"operation": "worktree_create", "repo": str(repo), "branch": args.branch, "destination": str(destination), "workspaces": args.workspace, "changes": [f"create worktree {destination}", *[f"bind to {x}" for x in args.workspace]], "blockers": blockers, "ready": not blockers}}, separators=(",", ":")))
if __name__ == "__main__": main()
