#!/usr/bin/env python3
"""Plan and safely fast-forward an Orcan parent Git checkout for Studio."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def git(
    path: Path, *arguments: str, timeout: int = 15
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(path), *arguments],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def output(result: subprocess.CompletedProcess[str]) -> str | None:
    return result.stdout.strip() if result.returncode == 0 else None


def inspect(path: Path, branch: str) -> dict[str, object]:
    resolved = path.resolve()
    if (
        not resolved.is_dir()
        or output(git(resolved, "rev-parse", "--is-inside-work-tree")) != "true"
    ):
        raise ValueError("path is not a Git working tree")
    current_branch = output(git(resolved, "symbolic-ref", "--quiet", "--short", "HEAD"))
    head = output(git(resolved, "rev-parse", "HEAD"))
    status = output(
        git(resolved, "status", "--porcelain=v1", "--untracked-files=normal")
    )
    dirty = bool(status) if status is not None else None
    remote_head = output(
        git(
            resolved,
            "ls-remote",
            "--heads",
            "origin",
            f"refs/heads/{branch}",
            timeout=20,
        )
    )
    remote_commit = remote_head.split()[0] if remote_head else None
    blockers: list[str] = []
    if dirty is None:
        blockers.append("cannot determine parent working-tree status")
    if current_branch != branch:
        blockers.append(
            f"parent is on {current_branch or 'detached HEAD'}, not {branch}"
        )
    if dirty:
        blockers.append("parent has uncommitted or untracked changes")
    if not head:
        blockers.append("parent has no HEAD commit")
    if not remote_commit:
        blockers.append(f"origin has no branch {branch}")
    return {
        "path": str(resolved),
        "branch": branch,
        "head": head,
        "remote_head": remote_commit,
        "current_branch": current_branch,
        "dirty": dirty,
        "operation": "git pull --ff-only",
        "ready": not blockers,
        "blockers": blockers,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "apply"))
    parser.add_argument("--path", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--expected-head")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    try:
        plan = inspect(Path(args.path), args.branch)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        raise SystemExit(2)

    if args.mode == "plan":
        print(json.dumps({"ok": True, "plan": plan}, separators=(",", ":")))
        return
    if not args.yes or not args.expected_head:
        print(
            json.dumps(
                {"ok": False, "error": "apply requires --expected-head and --yes"}
            )
        )
        raise SystemExit(2)
    if not plan["ready"] or plan["head"] != args.expected_head:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "parent changed or is not safe to update",
                    "plan": plan,
                }
            )
        )
        raise SystemExit(2)
    result = git(
        Path(plan["path"]), "pull", "--ff-only", "origin", args.branch, timeout=120
    )
    if result.returncode != 0:
        print(json.dumps({"ok": False, "error": result.stderr.strip(), "plan": plan}))
        raise SystemExit(1)
    updated = inspect(Path(plan["path"]), args.branch)
    print(
        json.dumps(
            {"ok": True, "before": plan["head"], "after": updated["head"]},
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
