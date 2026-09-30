#!/usr/bin/env python3
"""Emit a read-only, versioned Orcan Sandbox report for Orcan Studio."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shlex
import shutil
import subprocess
from pathlib import Path


def read_json(path: Path) -> dict[str, object]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def read_json_text(contents: str) -> dict[str, object]:
    try:
        return json.loads(contents)
    except json.JSONDecodeError:
        return {}


def git_output(path: Path, *arguments: str) -> str | None:
    """Return a small Git fact without invoking a shell or changing repository state."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *arguments],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def git_details(path: Path) -> dict[str, object]:
    common_dir = git_output(path, "rev-parse", "--git-common-dir")
    if not common_dir:
        return {}
    common_path = (
        (path / common_dir).resolve()
        if not Path(common_dir).is_absolute()
        else Path(common_dir)
    )
    branch = git_output(path, "symbolic-ref", "--quiet", "--short", "HEAD")
    status = git_output(path, "status", "--porcelain=v1", "--untracked-files=normal")
    upstream = git_output(
        path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"
    )
    ahead_behind = git_output(
        path, "rev-list", "--left-right", "--count", "HEAD...@{upstream}"
    )
    ahead: int | None = None
    behind: int | None = None
    if ahead_behind:
        try:
            ahead, behind = (int(value) for value in ahead_behind.split())
        except ValueError:
            pass
    return {
        "repository_id": hashlib.sha256(str(common_path).encode()).hexdigest()[:16],
        "git_common_dir": str(common_path),
        "origin_url": git_output(path, "config", "--get", "remote.origin.url"),
        "branch": branch,
        "dirty": bool(status),
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
    }


def classify_path(path: Path) -> dict[str, object]:
    """Classify a configured or managed path without modifying its Git state."""
    if not path.exists():
        return {"path": str(path), "kind": "missing", "writable": False}
    if not path.is_dir():
        return {"path": str(path), "kind": "file", "writable": os.access(path, os.W_OK)}
    git_marker = path / ".git"
    if git_marker.is_file():
        kind = "git_worktree"
    elif git_marker.is_dir():
        kind = "git_repository"
    else:
        kind = "directory"
    return {
        "path": str(path),
        "kind": kind,
        "writable": os.access(path, os.W_OK),
        **git_details(path),
    }


def context_snapshot(
    config_path: Path, projects_root: Path, home: Path
) -> dict[str, object]:
    """Return Studio-visible configuration and path membership, never secrets."""
    config = read_json(config_path)
    workspaces: list[dict[str, object]] = []
    for workspace in config.get("workspaces") or []:
        if not isinstance(workspace, dict):
            continue
        name = str(workspace.get("name") or "")
        projects: list[dict[str, object]] = []
        for project in workspace.get("projects") or []:
            if not isinstance(project, dict):
                continue
            raw_path = str(project.get("path") or "")
            if raw_path:
                path = Path(raw_path)
                item = classify_path(path)
                default_name = path.name
            else:
                item = {"path": "", "kind": "missing", "writable": False}
                default_name = "unnamed project"
            item["name"] = str(project.get("name") or default_name)
            projects.append(item)
        workspaces.append({"name": name, "projects": projects})
    managed_entries = (
        [
            classify_path(entry)
            for entry in sorted(projects_root.iterdir())
            if not entry.name.startswith(".")
        ]
        if projects_root.is_dir()
        else []
    )
    repositories: dict[str, dict[str, object]] = {}
    for workspace in workspaces:
        for project in workspace["projects"]:
            repository_id = project.get("repository_id")
            if not isinstance(repository_id, str):
                continue
            repository = repositories.setdefault(
                repository_id,
                {
                    "repository_id": repository_id,
                    "origin_url": project.get("origin_url"),
                    "git_common_dir": project.get("git_common_dir"),
                    "bindings": [],
                },
            )
            repository["bindings"].append(
                {
                    "workspace": workspace["name"],
                    "project": project["name"],
                    "path": project["path"],
                    "kind": project["kind"],
                }
            )
    raw = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    return {
        "configuration": {
            "state": "present" if config_path.is_file() else "missing",
            "revision": hashlib.sha256(raw).hexdigest()
            if config_path.is_file()
            else None,
        },
        "paths": {
            "workspace_metadata_root": str(home / "workspaces"),
            "managed_worktrees_root": str(projects_root / ".worktrees"),
        },
        "workspaces": workspaces,
        "managed_projects": managed_entries,
        "repositories": list(repositories.values()),
    }


def docker_probe(docker: str, image: str, container: str) -> dict[str, object]:
    """Return Docker facts without changing images, containers, or configuration."""
    if not shutil.which(docker):
        return {
            "available": False,
            "image": {"name": image, "present": False},
            "container": {"name": container, "state": "unavailable"},
        }

    try:
        daemon = (
            subprocess.run(
                [docker, "info"], capture_output=True, text=True, timeout=5, check=False
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        daemon = False
    if not daemon:
        return {
            "available": False,
            "image": {"name": image, "present": False},
            "container": {"name": container, "state": "unavailable"},
        }

    image_present = (
        subprocess.run(
            [docker, "image", "inspect", image],
            capture_output=True,
            text=True,
            check=False,
        ).returncode
        == 0
    )
    state = subprocess.run(
        [docker, "inspect", "--format", "{{.State.Status}}", container],
        capture_output=True,
        text=True,
        check=False,
    )
    container_state = state.stdout.strip() if state.returncode == 0 else "missing"
    agents: dict[str, object] = {}
    if image_present:
        manifest = subprocess.run(
            [
                docker,
                "run",
                "--rm",
                "--entrypoint",
                "cat",
                image,
                "/etc/orcan/agents.json",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if manifest.returncode == 0:
            reported_agents = read_json_text(manifest.stdout).get("agents", {})
            if isinstance(reported_agents, dict) and all(
                isinstance(name, str) and isinstance(available, bool)
                for name, available in reported_agents.items()
            ):
                agents = reported_agents
    return {
        "available": True,
        "image": {"name": image, "present": image_present},
        "container": {"name": container, "state": container_state},
        "agents": agents,
    }


def launch_flags(path: Path) -> dict[str, object]:
    """Flags of the last `orcan up` (credentials are never recorded)."""
    if not path.is_file():
        return {"recorded": False}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        parsed = shlex.split(value)
        values[key] = parsed[0] if parsed else ""
    flag = lambda key: values.get(key) == "1"  # noqa: E731
    return {
        "recorded": True,
        "docker": flag("WITH_DOCKER"),
        "git": flag("WITH_GIT"),
        "network": values.get("NETWORK_NAME") if flag("WITH_NETWORK") else None,
        "ttyd": flag("WITH_TTYD"),
        "ttyd_auth": flag("WITH_TTYD_AUTH"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=int, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--home", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--projects-root", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--container", required=True)
    parser.add_argument("--last-up", default="")
    args = parser.parse_args()

    docker = docker_probe(
        os.environ.get("ORCAN_STUDIO_DOCKER", "docker"), args.image, args.container
    )
    runtime_data = read_json(Path(args.runtime))
    report = {
        "protocol": {
            "name": "orcan-studio",
            "version": args.protocol,
            "methods": ["probe"],
        },
        "sandbox": {"version": args.version},
        "host": {
            "os": platform.system().lower(),
            "architecture": platform.machine().lower(),
        },
        "paths": {
            "home": str(Path(args.home)),
            "data": str(Path(args.data)),
            "projects_root": str(Path(args.projects_root)),
            "workspace_metadata_root": str(Path(args.home) / "workspaces"),
            "managed_worktrees_root": str(Path(args.projects_root) / ".worktrees"),
        },
        "capabilities": {
            "docker": bool(docker["available"]),
            "git": shutil.which("git") is not None,
            "managed_projects": True,
            "live_reconcile": True,
        },
        "runtime": {
            "config": "present" if Path(args.config).is_file() else "missing",
            "generated": "present" if Path(args.runtime).is_file() else "missing",
            "docker": docker,
            "resources": runtime_data.get("resources", {}),
            "launch": launch_flags(Path(args.last_up))
            if args.last_up
            else {"recorded": False},
        },
        "context": context_snapshot(
            Path(args.config), Path(args.projects_root), Path(args.home)
        ),
    }
    print(json.dumps(report, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
