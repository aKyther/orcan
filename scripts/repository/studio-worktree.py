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
    parser.add_argument("mode", choices=("plan", "remove-plan"))
    parser.add_argument("--repo"); parser.add_argument("--branch")
    parser.add_argument("--path")
    parser.add_argument("--worktrees-root", required=True); parser.add_argument("--workspace", action="append", default=[])
    args = parser.parse_args(); root = Path(args.worktrees_root).resolve()
    if args.mode == "remove-plan":
        if not args.path: parser.error("--path is required for remove-plan")
        path = Path(args.path).resolve()
        print(json.dumps({"ok": True, "plan": {"operation": "worktree_remove", "path": str(path), "exists": path.exists(), "changes": ["remove worktree registration", f"remove directory {path}"], "blockers": [] if path.exists() else ["worktree path does not exist"], "ready": path.exists(), "destructive": True}}, separators=(",", ":")))
        return
    if not args.repo or not args.branch: parser.error("--repo and --branch are required for plan")
    repo = Path(args.repo).resolve()
    destination = root / repo.name / args.branch
    blockers = []
    if run(repo, "rev-parse", "--is-inside-work-tree") != "true": blockers.append("parent is not a Git repository")
    if destination.exists(): blockers.append("managed worktree destination already exists")
    print(json.dumps({"ok": True, "plan": {"operation": "worktree_create", "repo": str(repo), "branch": args.branch, "destination": str(destination), "workspaces": args.workspace, "changes": [f"create worktree {destination}", *[f"bind to {x}" for x in args.workspace]], "blockers": blockers, "ready": not blockers}}, separators=(",", ":")))
if __name__ == "__main__": main()
