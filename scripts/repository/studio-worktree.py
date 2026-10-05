"""Read-only worktree plan consumed by Orcan Studio."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def run(repo: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def registry_entries(root: Path) -> dict[str, dict[str, object]]:
    """Read legacy and current registry entries without making list stateful."""
    try:
        raw = json.loads((root / "registry.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    entries = raw.get("worktrees") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        return {}
    return {
        str(Path(str(entry["path"])).resolve()): entry
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }


def segment(value: str) -> str:
    """Return a filesystem-safe, human-readable branch label."""
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    return normalized or "branch"


def worktree_project_name(root: Path, workspace: str, repo: Path, branch: str) -> str:
    """Make a stable project identity for one branch in one workspace.

    ``api--feature-auth`` keeps the source repository visually primary.  A
    short hash is added only when two distinct branch spellings normalize to
    the same path (for example ``feature/auth`` and ``feature-auth``).
    """
    base = f"{segment(repo.name)}--{segment(branch)}"
    destination = root / workspace / base
    if not destination.exists():
        return base
    existing_branch = run(destination, "symbolic-ref", "--quiet", "--short", "HEAD")
    if existing_branch == branch:
        return base
    return f"{base}--{hashlib.sha256(branch.encode()).hexdigest()[:6]}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        choices=("list", "branches", "plan", "apply", "remove-plan", "remove-apply"),
    )
    parser.add_argument("--repo")
    parser.add_argument("--branch")
    parser.add_argument("--path")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--remove-branch", action="store_true")
    parser.add_argument("--worktrees-root", required=True)
    parser.add_argument("--workspace", action="append", default=[])
    args = parser.parse_args()
    root = Path(args.worktrees_root).resolve()
    if args.mode == "branches":
        if not args.repo:
            parser.error("--repo is required for branches")
        repo = Path(args.repo).resolve()
        if run(repo, "rev-parse", "--is-inside-work-tree") != "true":
            print(
                json.dumps(
                    {
                        "ok": True,
                        "branches": [],
                        "blockers": ["source is not a Git repository"],
                    }
                )
            )
            return
        branches = (
            run(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads") or ""
        ).splitlines()
        print(json.dumps({"ok": True, "branches": branches}, separators=(",", ":")))
        return
    if args.mode == "list":
        entries = []
        registered = registry_entries(root)
        if root.is_dir():
            for path in sorted(item for item in root.glob("*/*") if item.is_dir()):
                if run(path, "rev-parse", "--is-inside-work-tree") != "true":
                    continue
                registration = registered.get(str(path.resolve()), {})
                entries.append(
                    {
                        "path": str(path.resolve()),
                        # New layout: <workspace>/<repo>--<branch>. Old layouts
                        # retain their registry labels, falling back to the old
                        # parent-folder interpretation when no registry exists.
                        "project": registration.get("project", path.parent.name),
                        "workspace": registration.get("workspace"),
                        "branch": run(
                            path, "symbolic-ref", "--quiet", "--short", "HEAD"
                        ),
                        "dirty": bool(run(path, "status", "--porcelain=v1")),
                    }
                )
        print(json.dumps({"ok": True, "worktrees": entries}, separators=(",", ":")))
        return
    if args.mode in {"remove-plan", "remove-apply"}:
        if not args.path:
            parser.error("--path is required for remove-plan")
        path = Path(args.path).resolve()
        branch = (
            run(path, "symbolic-ref", "--quiet", "--short", "HEAD")
            if path.exists()
            else None
        )
        git_dir = (
            run(path, "rev-parse", "--absolute-git-dir") if path.exists() else None
        )
        merged = (
            branch in (run(path, "branch", "--merged") or "").split()
            if branch
            else False
        )
        plan = {
            "operation": "worktree_remove",
            "path": str(path),
            "exists": path.exists(),
            "changes": ["remove worktree registration", f"remove directory {path}"],
            "blockers": [] if path.exists() else ["worktree path does not exist"],
            "ready": path.exists(),
            "destructive": True,
            "branch": branch,
            "remove_branch": args.remove_branch,
        }
        if args.remove_branch and not branch:
            plan["blockers"].append("worktree has no removable branch")
        if args.remove_branch and not merged:
            plan["blockers"].append("branch is not merged; refusing to delete it")
        plan["ready"] = not plan["blockers"]
        if args.mode == "remove-plan":
            print(json.dumps({"ok": True, "plan": plan}, separators=(",", ":")))
            return
        if not args.yes or not plan["ready"]:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "remove apply requires --yes and a ready plan",
                    }
                )
            )
            raise SystemExit(2)
        result = subprocess.run(
            ["orcan", "context", "worktree", "remove", "--path", str(path), "--force"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": result.stderr.strip() or "worktree remove failed",
                    }
                )
            )
            raise SystemExit(result.returncode)
        if args.remove_branch and git_dir and branch:
            deleted = subprocess.run(
                ["git", "--git-dir", git_dir, "branch", "-d", branch],
                capture_output=True,
                text=True,
                check=False,
            )
            if deleted.returncode:
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "error": deleted.stderr.strip()
                            or "worktree removed but branch deletion failed",
                        }
                    )
                )
                raise SystemExit(deleted.returncode)
        print(
            json.dumps(
                {
                    "ok": True,
                    "result": {
                        "operation": "worktree_remove",
                        "path": str(path),
                        "branch_removed": args.remove_branch,
                    },
                }
            )
        )
        return
    if not args.repo or not args.branch:
        parser.error("--repo and --branch are required for plan")
    repo = Path(args.repo).resolve()
    primary_workspace = args.workspace[0] if args.workspace else None
    project = (
        worktree_project_name(root, primary_workspace, repo, args.branch)
        if primary_workspace
        else None
    )
    destination = (
        root / primary_workspace / project
        if primary_workspace and project
        else root / repo.name / args.branch
    )
    blockers = []
    if run(repo, "rev-parse", "--is-inside-work-tree") != "true":
        blockers.append("parent is not a Git repository")
    existing_branches = (
        run(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads") or ""
    ).splitlines()
    if args.branch in existing_branches:
        blockers.append(
            "branch already exists in this Git source; choose a new name or attach its existing worktree"
        )
    if destination.exists():
        blockers.append("managed worktree destination already exists")
    plan = {
        "operation": "worktree_create",
        "repo": str(repo),
        "branch": args.branch,
        "project": project,
        "destination": str(destination),
        "workspaces": args.workspace,
        "changes": [
            f"create worktree {destination}",
            *[f"bind to {x}" for x in args.workspace],
        ],
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
    command = [
        "orcan",
        "context",
        "worktree",
        "create",
        "--repo",
        str(repo),
        "--branch",
        args.branch,
        "--path",
        str(destination),
    ]
    if primary_workspace and project:
        command += ["--workspace", primary_workspace, "--project", project]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": result.stderr.strip() or "worktree create failed",
                }
            )
        )
        raise SystemExit(result.returncode)
    for workspace in args.workspace[1:]:
        bind = subprocess.run(
            ["orcan", "context", "add", str(destination), "--workspace", workspace],
            capture_output=True,
            text=True,
            check=False,
        )
        if bind.returncode:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": f"worktree was created but bind to {workspace} failed: {bind.stderr.strip()}",
                    }
                )
            )
            raise SystemExit(bind.returncode)
    print(
        json.dumps(
            {
                "ok": True,
                "result": {"operation": "worktree_create", "path": str(destination)},
            }
        )
    )


if __name__ == "__main__":
    main()
