#!/usr/bin/env python3
"""Refresh clean parent repositories under the sandbox; leave linked worktrees alone."""

from __future__ import annotations

import argparse
import fcntl
import fnmatch
import json
import os
import signal
import subprocess
from collections import Counter
from contextlib import nullcontext
from pathlib import Path


class GitError(Exception):
    pass


def git(path: Path, *args: str, timeout: int = 15) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    for key in (
        "GIT_DIR",
        "GIT_COMMON_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    ):
        env.pop(key, None)
    env.update(
        GIT_TERMINAL_PROMPT="0",
        GIT_ASKPASS="/bin/false",
        SSH_ASKPASS="/bin/false",
        GIT_OPTIONAL_LOCKS="0",
    )
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o ConnectTimeout=10")
    command = ["git", "-C", str(path), *args]
    with subprocess.Popen(
        command,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                stdout, stderr = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
            except ProcessLookupError:
                process.communicate()
            raise GitError(
                "Git operation timed out; inspect this repository before retrying"
            ) from None
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def output(path, *args):
    result = git(path, *args)
    if result.returncode:
        raise GitError("Could not inspect repository")
    return result.stdout.strip()


def sandbox_root(explicit: str | None) -> Path:
    raw = explicit or os.environ.get("ORCAN_PROJECTS_ROOT")
    if not raw:
        config = Path(
            os.environ.get(
                "ORCAN_CONFIG_FILE",
                str(
                    Path(os.environ.get("ORCAN_HOME", Path.home() / ".config/orcan"))
                    / "orcan.config.json"
                ),
            )
        )
        if config.is_file():
            value = json.loads(config.read_text())
            if not isinstance(value, dict):
                raise ValueError("Configuration must be a JSON object")
            raw = value.get("projects_root")
            if raw is not None and (
                not isinstance(raw, str) or not Path(raw).is_absolute()
            ):
                raise ValueError("projects_root must be an absolute directory path")
    root = (
        Path(raw).expanduser()
        if raw
        else Path(os.environ.get("ORCAN_DATA", Path.home() / ".config/orcan"))
        / "sandbox"
    )
    if not root.is_absolute():
        raise ValueError("Sandbox root must be an absolute directory path")
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Sandbox root must be a directory")
    return root


def repositories(root: Path, excludes: list[str]):
    pending = [root]
    while pending:
        path = pending.pop()
        # Stop at repository boundaries, including bare repositories and worktrees.
        if (path / ".git").exists() or (
            (path / "HEAD").is_file() and (path / "objects").is_dir()
        ):
            yield path, None
            continue
        try:
            with os.scandir(path) as entries:
                children = []
                for entry in entries:
                    if entry.name.startswith(".") or entry.name in {
                        "node_modules",
                        "__pycache__",
                    }:
                        continue
                    if any(
                        fnmatch.fnmatchcase(entry.name, pattern) for pattern in excludes
                    ):
                        continue  # Exclusions prune before stat, including remote mounts.
                    if entry.is_dir(follow_symlinks=False):
                        children.append(Path(entry.path))
                pending.extend(sorted(children, reverse=True))
        except OSError:
            yield path, "Cannot scan directory"


def update(path: Path, dry_run: bool, timeout: int, seen: set[str]) -> dict:
    result = {"path": str(path), "status": "skipped"}
    try:
        if output(path, "rev-parse", "--is-bare-repository") == "true":
            return {**result, "reason": "Bare repository"}
        top = output(path, "rev-parse", "--show-toplevel")
        if Path(top).resolve() != path:
            return {**result, "reason": "Not a repository root"}
        common = output(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
        git_dir = output(path, "rev-parse", "--absolute-git-dir")
        if Path(common).resolve() != Path(git_dir).resolve():
            return {**result, "reason": "Linked worktree"}
        if output(path, "rev-parse", "--show-superproject-working-tree"):
            return {**result, "reason": "Submodule"}
        common = str(Path(common).resolve())
        if common in seen:
            return {**result, "reason": "Repository already visited"}
        seen.add(common)
        guard = (
            nullcontext(None)
            if dry_run
            else (Path(common) / "orcan-sandbox-pull.lock").open("a")
        )
        with guard as lock:
            if lock is not None:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return {
                        **result,
                        "reason": "Another sandbox pull owns this repository",
                    }
            if any(
                (Path(git_dir) / name).exists()
                for name in (
                    "MERGE_HEAD",
                    "CHERRY_PICK_HEAD",
                    "REVERT_HEAD",
                    "rebase-merge",
                    "rebase-apply",
                    "index.lock",
                )
            ):
                return {**result, "reason": "Git lock or operation in progress"}
            branch = output(path, "branch", "--show-current")
            if not branch:
                return {**result, "reason": "Detached HEAD"}
            result["branch"] = branch
            if output(path, "status", "--porcelain=v1", "--untracked-files=normal"):
                return {**result, "reason": "Uncommitted or untracked changes"}
            upstream = git(
                path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"
            )
            if upstream.returncode:
                return {**result, "reason": "No upstream configured"}
            result["upstream"] = upstream.stdout.strip()
            result["before"] = output(path, "rev-parse", "HEAD")
            if dry_run:
                return {
                    **result,
                    "status": "would_pull",
                    "reason": "Clean parent with upstream; no network request made",
                }
            pulled = git(
                path,
                "pull",
                "--ff-only",
                "--no-rebase",
                "--no-autostash",
                "--no-recurse-submodules",
                timeout=timeout,
            )
            if pulled.returncode:
                return {
                    **result,
                    "status": "error",
                    "reason": "Fast-forward pull failed; check upstream, network or divergent history",
                }
            after = output(path, "rev-parse", "HEAD")
            return {
                **result,
                "after": after,
                "status": "updated" if result["before"] != after else "unchanged",
            }
    except (GitError, OSError):
        # Raw Git stderr can expose remote URLs and credentials. Keep it out of bulk output.
        return {
            **result,
            "status": "error",
            "reason": "Git operation failed or timed out; inspect this repository",
        }


def main(argv=None):
    parser = argparse.ArgumentParser(prog="orcan sandbox", description=__doc__)
    parser.add_argument("command", choices=["pull"])
    parser.add_argument(
        "--root", help="Sandbox root; defaults to configured projects_root"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect eligibility without fetching or pulling",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Skip matching directory names before inspecting them",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Per-repository pull timeout in seconds (1..600)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit compact results without successful Git output",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 600 or any(
        not pattern or "/" in pattern for pattern in args.exclude
    ):
        parser.error(
            "timeout must be 1..600 and exclusions must be directory name patterns without slashes"
        )
    try:
        root = sandbox_root(args.root)
    except (ValueError, OSError):
        parser.error(
            "Cannot resolve sandbox root; check --root, projects_root and directory availability"
        )
    seen, results = set(), []
    for path, error in repositories(root, args.exclude):
        results.append(
            {"path": str(path), "status": "error", "reason": error}
            if error
            else update(path, args.dry_run, args.timeout, seen)
        )
    counts = {
        status: 0
        for status in ("updated", "unchanged", "skipped", "would_pull", "error")
    }
    counts.update(Counter(item["status"] for item in results))
    if args.json:
        print(
            json.dumps(
                {
                    "root": str(root),
                    "dry_run": args.dry_run,
                    "counts": counts,
                    "results": results,
                },
                separators=(",", ":"),
            )
        )
    else:
        for item in results:
            label = str(Path(item["path"]).relative_to(root))
            print(
                f"{item['status']}: {label}"
                + (f" ({item['reason']})" if item.get("reason") else "")
            )
        print(
            "Summary: "
            + ", ".join(f"{status}={count}" for status, count in counts.items())
        )
    return 1 if counts["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
