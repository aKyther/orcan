#!/usr/bin/env python3
"""Apply cind.config.json into .env, runtime config, workspace artifacts, and Compose mounts."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path


SENSITIVE = {"/", "/home", "/root", "/etc", "/usr", "/var", "/opt"}
DEFAULT_DEVELOPER_WORKSPACES = "/home/developer/workspaces"


def die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def resolve_abs(path: str, label: str) -> Path:
    if "~" in path:
        die(f"{label} must not contain ~ (got: {path})")
    p = Path(path)
    if not p.is_absolute():
        die(f"{label} must be an absolute path (got: {path})")
    if not p.exists():
        die(f"{label} does not exist: {path}")
    if not p.is_dir():
        die(f"{label} is not a directory: {path}")
    resolved = p.resolve()
    if str(resolved) in SENSITIVE:
        die(f"refusing sensitive path for {label}: {resolved}")
    home = Path.home().resolve()
    if resolved == home:
        die(f"refusing to mount entire home for {label}: {resolved}")
    if not os.access(resolved, os.R_OK):
        die(f"{label} is not readable: {resolved}")
    return resolved


def ensure_dir(path: Path, label: str) -> Path:
    if "~" in str(path):
        die(f"{label} must not contain ~")
    if not path.is_absolute():
        die(f"{label} must be an absolute path (got: {path})")
    resolved = path.resolve()
    if str(resolved) in SENSITIVE:
        die(f"refusing sensitive path for {label}: {resolved}")
    home = Path.home().resolve()
    if resolved == home:
        die(f"refusing to use entire home for {label}: {resolved}")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def ensure_env_key(env_path: Path, key: str, value: str) -> None:
    text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    lines = text.splitlines()
    pattern = re.compile(rf"^{re.escape(key)}=")
    replaced = False
    out: list[str] = []
    for line in lines:
        if pattern.match(line):
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        if out and out[-1] != "":
            out.append("")
        out.append(f"{key}={value}")
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def env_has_key(env_path: Path, key: str) -> bool:
    if not env_path.exists():
        return False
    pattern = re.compile(rf"^{re.escape(key)}=")
    return any(pattern.match(line) for line in env_path.read_text(encoding="utf-8").splitlines())


def ensure_env_key_unless_set(env_path: Path, key: str, value: str) -> None:
    """Set key only when missing — preserves host-specific .env overrides (e.g. CPUS)."""
    if env_has_key(env_path, key):
        return
    ensure_env_key(env_path, key, value)


def remove_env_key(env_path: Path, key: str) -> None:
    if not env_path.exists():
        return
    pattern = re.compile(rf"^{re.escape(key)}=")
    lines = [
        line
        for line in env_path.read_text(encoding="utf-8").splitlines()
        if not pattern.match(line)
    ]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_config(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(f"invalid JSON in {path}: {exc}")
    if not isinstance(data, dict):
        die(f"config root must be an object: {path}")
    return data


def normalize_workspaces_raw(cfg: dict) -> list[dict]:
    if cfg.get("projects_dir"):
        die(
            "'projects_dir' was removed; use workspaces[] or workspace.projects[] "
            "(see cind.config.example.json)"
        )

    raw_list = cfg.get("workspaces")
    if raw_list is not None:
        if not isinstance(raw_list, list) or not raw_list:
            die("workspaces must be a non-empty array")
        return raw_list

    ws_raw = cfg.get("workspace")
    if isinstance(ws_raw, dict):
        merged = dict(ws_raw)
        if cfg.get("projects") and not merged.get("projects"):
            merged["projects"] = cfg["projects"]
        if merged.get("projects"):
            return [merged]

    if cfg.get("projects"):
        wrapper: dict = {}
        if isinstance(ws_raw, dict):
            wrapper.update(ws_raw)
        wrapper["projects"] = cfg["projects"]
        return [wrapper]

    die("config requires workspaces[], workspace.projects[], or legacy projects[]")


def default_workspace_root(ws_name: str, explicit: str) -> str:
    if explicit:
        return explicit
    return f"{DEFAULT_DEVELOPER_WORKSPACES.rstrip('/')}/{ws_name}"


def parse_projects(
    projects_raw: list,
    ws_root: str,
    label: str,
) -> list[dict]:
    if not isinstance(projects_raw, list) or not projects_raw:
        die(f"{label} must contain at least one project")

    projects: list[dict] = []
    seen_paths: set[str] = set()
    seen_names: set[str] = set()

    for i, item in enumerate(projects_raw):
        if not isinstance(item, dict):
            die(f"{label}[{i}] must be an object")
        if item.get("alias"):
            die(
                f"{label}[{i}].alias was removed; use name as the subdirectory "
                f"under the workspace root"
            )
        if item.get("mount"):
            die(
                f"{label}[{i}].mount was removed; all projects use path parity "
                f"(host path = container path) with a symlink under the workspace root"
            )
        if item.get("role"):
            die(f"{label}[{i}].role was removed; use name and path only")
        name = str(item.get("name") or "").strip()
        path = str(item.get("path") or "").strip()
        if not name or not path:
            die(f"{label}[{i}] requires name and path")
        if name in seen_names:
            die(f"duplicate project name in {label}: {name}")
        if ".." in Path(name).parts or name.startswith("/"):
            die(f"{label}[{i}].name must be a simple directory name (got: {name})")

        resolved = resolve_abs(path, f"{label}[{i}].path")
        path_key = str(resolved)
        if path_key in seen_paths:
            die(f"duplicate project path in {label}: {path_key}")
        seen_names.add(name)
        seen_paths.add(path_key)

        workspace_path = f"{ws_root.rstrip('/')}/{name}"

        windows_raw = item.get("windows") or []
        if windows_raw and not isinstance(windows_raw, list):
            die(f"{label}[{i}].windows must be a list")
        windows: list[dict] = []
        for j, win in enumerate(windows_raw):
            if not isinstance(win, dict):
                die(f"{label}[{i}].windows[{j}] must be an object")
            win_name = str(win.get("name") or "shell").strip()
            windows.append(
                {
                    "name": win_name,
                    "icon": str(win.get("icon") or "").strip(),
                    "dir": str(win.get("dir") or ".").strip(),
                    "command": str(win.get("command") or "").strip(),
                }
            )

        projects.append(
            {
                "name": name,
                "path": path_key,
                "workspace_path": workspace_path,
                "container_path": path_key,
                "windows": windows,
            }
        )

    return projects


def build_workspace_entry(
    cfg: dict,
    ws_raw: dict,
    ws_index: int,
    ws_count: int,
    repo_root: Path,
    seen_names: set[str],
    seen_roots: set[str],
    seen_tmux: set[str],
) -> dict:
    if not isinstance(ws_raw, dict):
        die(f"workspaces[{ws_index}] must be an object")

    projects_raw = ws_raw.get("projects") or []
    label = f"workspaces[{ws_index}].projects"
    ws_name = str(ws_raw.get("name") or "").strip()
    if not ws_name and projects_raw:
        ws_name = str(projects_raw[0].get("name") or f"workspace-{ws_index + 1}").strip()
    if not ws_name:
        die(f"workspaces[{ws_index}] requires name (or projects[].name)")

    if ws_name in seen_names:
        die(f"duplicate workspace name: {ws_name}")
    seen_names.add(ws_name)

    if ws_raw.get("default_project") or cfg.get("default_project"):
        die(
            "default_project was removed; the agent starts in the workspace root. "
            "Agents start in the workspace root."
        )

    if ws_raw.get("mount_mode"):
        die(
            f"workspaces[{ws_index}].mount_mode was removed; all projects use path parity "
            f"with symlinks under {DEFAULT_DEVELOPER_WORKSPACES}/<name>"
        )

    explicit_root = str(ws_raw.get("root") or "").strip()
    if explicit_root:
        die(
            f"workspaces[{ws_index}].root was removed; workspace roots are always "
            f"{DEFAULT_DEVELOPER_WORKSPACES}/<name>"
        )
    ws_root = default_workspace_root(ws_name, "")
    if not ws_root.startswith("/"):
        die(f"workspaces[{ws_index}].root must be an absolute path (got: {ws_root})")
    if ws_root in SENSITIVE:
        die(f"refusing sensitive workspaces[{ws_index}].root: {ws_root}")
    if ws_root in seen_roots:
        die(f"duplicate workspace root: {ws_root}")
    seen_roots.add(ws_root)

    meta_raw = str(ws_raw.get("meta_path") or "").strip()
    if meta_raw:
        die(
            f"workspaces[{ws_index}].meta_path was removed; workspace roots are always "
            f"{DEFAULT_DEVELOPER_WORKSPACES}/<name> (host meta: .cind/workspaces/<name>/)"
        )
    meta_path = ensure_dir(
        repo_root / ".cind" / "workspaces" / ws_name,
        f"workspace meta for {ws_name}",
    )

    if "tmux" in ws_raw:
        die(
            f"workspaces[{ws_index}].tmux was removed; tmux session name is always "
            f"the workspace name ({ws_name!r}). "
            f"Use root-level \"tmux\": {{ \"initial_windows\": … }} for window defaults only."
        )

    tmux_name = ws_name
    if tmux_name in seen_tmux:
        die(f"duplicate tmux session name: {tmux_name}")
    seen_tmux.add(tmux_name)

    projects = parse_projects(projects_raw, ws_root, label)

    for p in projects:
        wp = p["workspace_path"]
        prefix = ws_root.rstrip("/") + "/"
        if not wp.startswith(prefix):
            die(
                f"internal error: project {p['name']!r} workspace_path {wp!r} "
                f"is not under workspace root {ws_root!r}"
            )

    workspace = {
        "name": ws_name,
        "root": ws_root,
        "meta_path": str(meta_path),
        "enabled": ws_raw.get("enabled", True) is not False,
        "tmux_session": tmux_name,
        "project_count": len(projects),
        "projects": projects,
    }
    return workspace


def primary_workspace(workspaces: list[dict]) -> dict:
    for ws in workspaces:
        if ws.get("enabled") is not False:
            return ws
    return workspaces[0]


def prune_stale_workspace_metas(repo_root: Path, active_names: set[str]) -> None:
    """Remove .cind/workspaces/<name>/ dirs for workspaces no longer in config."""
    host_workspaces = repo_root / ".cind" / "workspaces"
    if not host_workspaces.is_dir():
        return
    for child in sorted(host_workspaces.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if child.name in active_names:
            continue
        shutil.rmtree(child)
        print(f"removed stale workspace meta: {child}")


def write_compose_projects(workspaces: list[dict], repo_root: Path) -> str:
    """One bind for all workspace metas + parity binds for every project path."""
    host_workspaces = ensure_dir(
        repo_root / ".cind" / "workspaces", "workspace metas root"
    )
    lines = [
        "# Generated by apply-config.py — do not edit by hand.",
        "services:",
        "  cind:",
        "    volumes:",
        # Single parent mount — avoids per-workspace bind overlap / cross-visible trees.
        f"      - {host_workspaces}:{DEFAULT_DEVELOPER_WORKSPACES}",
    ]

    parity_paths: set[str] = set()
    for ws in workspaces:
        for project in ws["projects"]:
            parity_paths.add(project["path"])

    for path in sorted(parity_paths):
        lines.append(f"      - {path}:{path}")
    return "\n".join(lines) + "\n"


def write_workspace_manifest(runtime: dict) -> dict:
    return {
        "workspaces": [
            {
                "name": ws["name"],
                "root": ws["root"],
                "meta_path": ws["meta_path"],
                "tmux_session": ws["tmux_session"],
                "project_count": ws["project_count"],
                "projects": ws["projects"],
            }
            for ws in runtime["workspaces"]
        ],
    }


def write_code_workspace(
    repo_root: Path,
    workspace: dict,
    projects: list[dict],
    *,
    suffix: str,
    use_container_paths: bool,
) -> Path:
    runtime_dir = repo_root / ".cind"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "-", workspace["name"]).strip("-") or "workspace"
    out_path = runtime_dir / f"{safe_name}.{suffix}.code-workspace"

    ws_folder = workspace["root"] if use_container_paths else workspace["meta_path"]
    folders = [{"name": workspace["name"], "path": ws_folder}]
    for p in projects:
        folders.append(
            {
                "name": p["name"],
                "path": (
                    p["container_path"]
                    if use_container_paths
                    else p["path"]
                ),
            }
        )

    payload = {
        "folders": folders,
        "settings": {"files.exclude": {"**/.git": True}},
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out_path


def build_from_config(cfg: dict, repo_root: Path) -> dict:
    if cfg.get("default_project"):
        die(
            "default_project was removed; agents start in the workspace root."
        )
    if cfg.get("default_workspace"):
        die("default_workspace was removed; list workspaces[] only (min. one entry)")

    raw_list = normalize_workspaces_raw(cfg)
    ws_count = len(raw_list)
    seen_names: set[str] = set()
    seen_roots: set[str] = set()
    seen_tmux: set[str] = set()

    workspaces: list[dict] = []
    for i, ws_raw in enumerate(raw_list):
        workspaces.append(
            build_workspace_entry(
                cfg, ws_raw, i, ws_count, repo_root, seen_names, seen_roots, seen_tmux
            )
        )

    primary_ws = primary_workspace(workspaces)
    container_project_dir = primary_ws["root"]

    ttyd = cfg.get("ttyd") or {}
    resources = cfg.get("resources") or {}
    if not isinstance(ttyd, dict) or not isinstance(resources, dict):
        die("ttyd and resources must be objects")

    tmux_cfg = cfg.get("tmux") if isinstance(cfg.get("tmux"), dict) else {}
    initial_windows = int(tmux_cfg.get("initial_windows", 3))
    if initial_windows < 1:
        initial_windows = 1
    if initial_windows > 9:
        initial_windows = 9
    window_prefix = str(tmux_cfg.get("window_prefix") or "tab").strip() or "tab"

    runtime: dict = {
        "workspaces": workspaces,
        "tmux": {
            "initial_windows": initial_windows,
            "window_prefix": window_prefix,
        },
        "ttyd": {
            "port": int(ttyd.get("port", 7681)),
            "host_port": int(ttyd.get("host_port", ttyd.get("port", 7681))),
            "font_size": int(ttyd.get("font_size", 22)),
        },
        "resources": {
            "cpus": resources.get("cpus", 8),
            "memory": str(resources.get("memory", "16g")),
            "shm_size": str(resources.get("shm_size", "2g")),
            "tmpfs_size": str(resources.get("tmpfs_size", "2g")),
        },
    }

    project_paths = [p["path"] for ws in workspaces for p in ws["projects"]]

    return {
        "runtime": runtime,
        "project_dir": str(repo_root),
        "container_project_dir": container_project_dir,
        "project_paths": project_paths,
        "primary_workspace": primary_ws,
        "workspaces": workspaces,
    }


def synthesize_from_env(project_dir: str, repo_root: Path) -> dict:
    pd = resolve_abs(project_dir, "PROJECT_DIR")
    ws_name = pd.name
    ws_root = default_workspace_root(ws_name, "")
    meta_path = ensure_dir(repo_root / ".cind" / "workspaces" / ws_name, "workspace meta")
    projects = [
        {
            "name": pd.name,
            "path": str(pd),
            "workspace_path": f"{ws_root}/{pd.name}",
            "container_path": str(pd),
            "windows": [],
        }
    ]
    workspace = {
        "name": ws_name,
        "root": ws_root,
        "meta_path": str(meta_path),
        "enabled": True,
        "tmux_session": ws_name,
        "project_count": 1,
        "projects": projects,
    }
    runtime = {
        "workspaces": [workspace],
        "tmux": {"initial_windows": 3, "window_prefix": "tab"},
        "ttyd": {"port": 7681, "host_port": 7681, "font_size": 22},
        "resources": {
            "cpus": 8,
            "memory": "16g",
            "shm_size": "2g",
            "tmpfs_size": "2g",
        },
    }
    return {
        "runtime": runtime,
        "project_dir": str(pd),
        "container_project_dir": ws_root,
        "project_paths": [str(pd)],
        "primary_workspace": workspace,
        "workspaces": [workspace],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="", help="Path to cind.config.json")
    parser.add_argument("--root", default="", help="Repository root")
    parser.add_argument("--project-dir", default="", help="Fallback PROJECT_DIR")
    args = parser.parse_args()

    root = Path(args.root or Path.cwd()).resolve()
    env_path = root / ".env"
    example = root / ".env.example"
    runtime_dir = root / ".cind"
    runtime_path = runtime_dir / "runtime-config.json"
    compose_path = runtime_dir / "compose-projects.generated.yml"
    manifest_path = runtime_dir / "workspace.manifest.json"

    if not env_path.exists():
        if not example.exists():
            die("missing .env and .env.example")
        env_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")

    config_path = Path(args.config) if args.config else None
    if config_path is not None and not config_path.is_absolute():
        config_path = (root / config_path).resolve()

    if config_path and config_path.is_file():
        built = build_from_config(load_config(config_path), root)
        print(f"Applied config: {config_path}")
    else:
        project_dir = args.project_dir or os.environ.get("PROJECT_DIR") or str(root)
        built = synthesize_from_env(project_dir, root)
        print("No CONFIG file; synthesized single-repo workspace from PROJECT_DIR")

    runtime_dir.mkdir(parents=True, exist_ok=True)
    active_names = {ws["name"] for ws in built["workspaces"] if ws.get("enabled") is not False}
    prune_stale_workspace_metas(root, active_names)
    # Drop stale *.code-workspace files for removed workspaces
    for path in runtime_dir.glob("*.container.code-workspace"):
        stem = path.name[: -len(".container.code-workspace")]
        if stem not in active_names and stem != "workspace":
            path.unlink(missing_ok=True)
            print(f"removed stale {path.name}")
    for path in runtime_dir.glob("*.host.code-workspace"):
        stem = path.name[: -len(".host.code-workspace")]
        if stem not in active_names and stem != "workspace":
            path.unlink(missing_ok=True)
            print(f"removed stale {path.name}")

    runtime_path.write_text(
        json.dumps(built["runtime"], indent=2) + "\n", encoding="utf-8"
    )
    compose_path.write_text(
        write_compose_projects(built["workspaces"], root),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(write_workspace_manifest(built["runtime"]), indent=2) + "\n",
        encoding="utf-8",
    )

    code_workspace_paths: list[Path] = []
    for ws in built["workspaces"]:
        code_workspace_paths.append(
            write_code_workspace(
                root, ws, ws["projects"], suffix="container", use_container_paths=True
            )
        )
        write_code_workspace(
            root, ws, ws["projects"], suffix="host", use_container_paths=False
        )

    primary_ws = built["primary_workspace"]
    ensure_env_key(env_path, "PROJECT_DIR", built["project_dir"])
    ensure_env_key(env_path, "CONTAINER_PROJECT_DIR", built["container_project_dir"])
    remove_env_key(env_path, "PROJECTS_DIR")
    remove_env_key(env_path, "PROJECT_ROOTS")
    remove_env_key(env_path, "DEFAULT_WORKSPACE")
    ensure_env_key(env_path, "CIND_CONFIG_HOST", str(runtime_path))
    ensure_env_key(env_path, "CIND_CONFIG", "/etc/cind/config.json")
    ensure_env_key(env_path, "CIND_COMPOSE_PROJECTS", str(compose_path))
    ensure_env_key(env_path, "CIND_WORKSPACE_MANIFEST", str(manifest_path))
    ensure_env_key(env_path, "WORKSPACE_ROOT", primary_ws["root"])
    ensure_env_key(env_path, "WORKSPACE_NAME", primary_ws["name"])
    ensure_env_key(env_path, "WORKSPACE_META_PATH", primary_ws["meta_path"])

    ttyd = built["runtime"]["ttyd"]
    resources = built["runtime"]["resources"]
    ensure_env_key_unless_set(env_path, "TTYD_PORT", str(ttyd["port"]))
    ensure_env_key_unless_set(env_path, "TTYD_HOST_PORT", str(ttyd["host_port"]))
    ensure_env_key_unless_set(env_path, "TTYD_FONT_SIZE", str(ttyd["font_size"]))
    ensure_env_key_unless_set(env_path, "CPUS", str(resources["cpus"]))
    ensure_env_key_unless_set(env_path, "MEMORY", str(resources["memory"]))
    ensure_env_key_unless_set(env_path, "SHM_SIZE", str(resources["shm_size"]))
    ensure_env_key_unless_set(env_path, "TMPFS_SIZE", str(resources["tmpfs_size"]))

    print(f"PROJECT_DIR={built['project_dir']} (orchestrator — where you run make)")
    print(f"WORKSPACE_ROOT={primary_ws['root']} (agent/tmux start directory in container)")
    print(f"workspaces: {len(built['workspaces'])} (one tmux session each)")
    for ws in built["workspaces"]:
        print(
            f"  - {ws['name']} @ {ws['root']} "
            f"(repos={ws['project_count']})"
        )
        print(f"    meta: {ws['meta_path']}")
        for p in ws["projects"]:
            print(
                f"      {p['name']}: {p['path']} (symlink → {p['workspace_path']})"
            )
    print(f"runtime config: {runtime_path}")
    print(f"compose mounts: {compose_path}")
    for path in code_workspace_paths:
        print(f"code-workspace (container): {path}")


if __name__ == "__main__":
    main()
