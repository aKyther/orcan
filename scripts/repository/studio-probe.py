"""Emit a read-only, versioned Orcan Sandbox report for Orcan Studio."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import platform
import shlex
import shutil
import subprocess
from pathlib import Path

from defaults import RESOURCE_DEFAULTS, TTYD_DEFAULTS
from git_worktrees import managed_worktrees_root


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


def indexed_workspaces(index_path: Path) -> list[dict[str, object]]:
    """Re-classify the last synced workspace index without trusting stale facts."""
    index = read_json(index_path)
    workspaces: list[dict[str, object]] = []
    for workspace in index.get("workspaces") or []:
        if not isinstance(workspace, dict) or workspace.get("enabled") is False:
            continue
        name = workspace.get("name")
        if not isinstance(name, str) or not name:
            continue
        projects: list[dict[str, object]] = []
        for project in workspace.get("projects") or []:
            if not isinstance(project, dict):
                continue
            raw_path = project.get("path")
            if not isinstance(raw_path, str) or not raw_path:
                continue
            path = Path(raw_path)
            item = classify_path(path)
            item["name"] = str(project.get("name") or path.name)
            projects.append(item)
        workspaces.append({"name": name, "projects": projects})
    return workspaces


def context_snapshot(
    config_path: Path, projects_root: Path, workspace_index: Path, instance: str = ""
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
    if not workspaces:
        workspaces = indexed_workspaces(workspace_index)
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
    # The worktree registry is Orcan's source of truth for repositories used to
    # create branches. Regular configured Git mounts remain distinct: they may
    # be updated only while clean, and never gain the worktree-parent role.
    worktrees_root = managed_worktrees_root(projects_root, instance)
    registry = read_json(worktrees_root / "registry.json")
    parent_counts: dict[str, int] = {}
    for entry in registry.get("worktrees") or []:
        if not isinstance(entry, dict):
            continue
        raw_repo = entry.get("repo")
        if not isinstance(raw_repo, str) or not raw_repo:
            continue
        path = str(Path(raw_repo).expanduser().resolve())
        parent_counts[path] = parent_counts.get(path, 0) + 1

    update_targets: dict[str, dict[str, object]] = {}

    def add_update_target(raw_path: str, *, role: str, worktree_count: int = 0) -> None:
        path = str(Path(raw_path).expanduser().resolve())
        item = classify_path(Path(path))
        # Directories and files are deliberately not update targets.
        if item.get("kind") != "git_repository":
            return
        # A mount-as-is is a read-only convenience target, never a place where
        # Studio should compete with local work. Dirty mounts stay out of the
        # selector entirely; studio-parent.py checks again before git pull.
        if role == "configured_mount" and item.get("dirty"):
            return
        existing = update_targets.get(path)
        if existing and existing.get("role") == "worktree_parent":
            return
        item.update(
            {
                "name": Path(path).name or path,
                "role": role,
                "worktree_count": worktree_count,
                "read_only": role == "configured_mount",
                "eligible": not bool(item.get("dirty")),
            }
        )
        update_targets[path] = item

    for path, count in parent_counts.items():
        add_update_target(path, role="worktree_parent", worktree_count=count)
    for workspace in workspaces:
        for project in workspace["projects"]:
            path = project.get("path")
            if isinstance(path, str) and path:
                add_update_target(path, role="configured_mount")
    raw = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    source = (
        "config" if config_path.is_file() else "runtime_index" if workspaces else "none"
    )
    return {
        "configuration": {
            "state": "present"
            if source == "config"
            else "runtime_index"
            if source == "runtime_index"
            else "missing",
            "source": source,
            "editable": source == "config",
            "path": str(config_path),
            "revision": hashlib.sha256(raw).hexdigest()
            if config_path.is_file()
            else None,
        },
        "paths": {
            "workspace_metadata_root": str(workspace_index.parent),
            "managed_worktrees_root": str(worktrees_root),
        },
        "workspaces": workspaces,
        "managed_projects": managed_entries,
        "repositories": list(repositories.values()),
        "update_targets": sorted(
            update_targets.values(),
            key=lambda target: (
                target.get("role") != "worktree_parent",
                str(target.get("name") or "").lower(),
            ),
        ),
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
    flag = lambda key: values.get(key) == "1"
    return {
        "recorded": True,
        "docker": flag("WITH_DOCKER"),
        "git": flag("WITH_GIT"),
        "network": values.get("NETWORK_NAME") if flag("WITH_NETWORK") else None,
        "ttyd": flag("WITH_TTYD"),
        "ttyd_auth": flag("WITH_TTYD_AUTH"),
    }


def studio_control(
    context: dict[str, object],
    docker: dict[str, object],
    runtime_data: dict[str, object],
    launch: dict[str, object],
) -> dict[str, object]:
    """Describe Studio controls; the desktop app never infers write authority."""
    configuration = context["configuration"]
    editable = bool(configuration.get("editable"))
    context_source = "orcan.config.json" if editable else "synced workspace index"
    context_reason = (
        "Orcan configuration is available for planned context changes."
        if editable
        else "Reconnect to the Orcan instance that owns orcan.config.json."
    )
    docker_available = bool(docker.get("available"))
    container = docker.get("container") or {}
    agents = docker.get("agents") or {}
    resources = runtime_data.get("resources") or {}
    resource_value = (
        " · ".join(
            part
            for part in (
                f"CPU {resources.get('cpus')}"
                if resources.get("cpus") is not None
                else None,
                f"RAM {resources.get('memory')}" if resources.get("memory") else None,
            )
            if part
        )
        or "Not reported"
    )
    agent_value = (
        " · ".join(name for name, enabled in agents.items() if enabled)
        or "Not reported"
    )
    ssh_agent = bool(os.environ.get("SSH_AUTH_SOCK"))
    terminal = (
        "ttyd protected"
        if launch.get("ttyd_auth")
        else "ttyd public"
        if launch.get("ttyd")
        else "local only"
    )
    access_value = " · ".join(
        (
            terminal,
            "Docker socket" if launch.get("docker") else "no Docker socket",
            "Git/SSH access" if launch.get("git") else "no Git/SSH access",
        )
    )
    return {
        "operations": {
            "context_edit": {"available": editable, "reason": context_reason},
            "context_sync": {"available": editable, "reason": context_reason},
            "parent_update": {
                "available": shutil.which("git") is not None,
                "reason": "Orcan rechecks branch, cleanliness, and origin before git pull --ff-only.",
            },
            "runtime_lifecycle": {
                "available": docker_available,
                "reason": "Docker is unavailable on this Orcan instance."
                if not docker_available
                else "Start, stop, and restart use Orcan's recorded launch flags.",
            },
        },
        "settings": [
            {
                "id": "context",
                "label": "Workspace context",
                "state": "editable" if editable else "locked",
                "value": context_source,
                "detail": context_reason,
                "action": "contexts",
            },
            {
                "id": "lifecycle",
                "label": "Container lifecycle",
                "state": "editable" if docker_available else "locked",
                "value": str(container.get("state") or "unavailable"),
                "detail": "Start, stop, and restart are available. Restart reuses Orcan's recorded launch flags."
                if docker_available
                else "Docker is unavailable on this Orcan instance.",
                "action": "runtime",
            },
            {
                "id": "resources",
                "label": "Container resources",
                "state": "locked",
                "value": resource_value,
                "detail": "CPU and memory are supplied at container creation; Studio reports them but does not rewrite Docker start configuration.",
            },
            {
                "id": "agents",
                "label": "Agent tools",
                "state": "locked",
                "value": agent_value,
                "detail": "The tool set belongs to the Orcan image and changes only when that image is built.",
            },
            {
                "id": "environment",
                "label": "Environment values",
                "state": "locked",
                "value": "Protected",
                "detail": "Environment is read when the container starts. Values, including possible secrets, are never displayed or edited here.",
            },
            {
                "id": "access",
                "label": "Access exposure",
                "state": "locked",
                "value": access_value,
                "detail": "Access flags come from the recorded Orcan launch. Studio can replay them, but does not silently change exposure.",
            },
            {
                "id": "git_auth",
                "label": "Git authentication",
                "state": "locked",
                "value": "SSH agent available"
                if ssh_agent
                else "No SSH agent reported",
                "detail": "Repository cloning runs through Orcan on this machine. Studio never reads or transfers SSH keys; private repository access is checked by Git during the clone.",
            },
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=int, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--home", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--projects-root", required=True)
    parser.add_argument("--workspace-index", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--container", required=True)
    parser.add_argument("--last-up", default="")
    parser.add_argument("--instance", default="")
    args = parser.parse_args()

    docker = docker_probe(
        os.environ.get("ORCAN_STUDIO_DOCKER", "docker"), args.image, args.container
    )
    runtime_data = read_json(Path(args.runtime))
    launch = launch_flags(Path(args.last_up)) if args.last_up else {"recorded": False}
    context = context_snapshot(
        Path(args.config),
        Path(args.projects_root),
        Path(args.workspace_index),
        args.instance,
    )
    worktrees_root = managed_worktrees_root(Path(args.projects_root), args.instance)
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
            "user": getpass.getuser(),
        },
        "paths": {
            "home": str(Path(args.home)),
            "data": str(Path(args.data)),
            "cache": str(Path(args.data) / "cache"),
            "projects_root": str(Path(args.projects_root)),
            "workspace_metadata_root": str(Path(args.workspace_index).parent),
            "managed_worktrees_root": str(worktrees_root),
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
            "defaults": {"resources": RESOURCE_DEFAULTS, "ttyd": TTYD_DEFAULTS},
            "launch": launch,
        },
        "context": context,
        "control": studio_control(context, docker, runtime_data, launch),
    }
    print(json.dumps(report, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
