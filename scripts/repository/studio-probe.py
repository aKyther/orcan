#!/usr/bin/env python3
"""Emit a read-only, versioned Orcan Sandbox report for Orcan Studio."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path


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
    return {"path": str(path), "kind": kind, "writable": os.access(path, os.W_OK)}


def context_snapshot(
    config_path: Path, projects_root: Path, home: Path
) -> dict[str, object]:
    """Return Studio-visible configuration and path membership, never secrets."""
    config: dict[str, object] = {}
    if config_path.is_file():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            config = {}
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
    return {
        "available": True,
        "image": {"name": image, "present": image_present},
        "container": {"name": container, "state": container_state},
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
    args = parser.parse_args()

    docker = docker_probe(
        os.environ.get("ORCAN_STUDIO_DOCKER", "docker"), args.image, args.container
    )
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
        },
        "context": context_snapshot(
            Path(args.config), Path(args.projects_root), Path(args.home)
        ),
    }
    print(json.dumps(report, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
