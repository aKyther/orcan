#!/usr/bin/env python3
"""Apply cind.config.json into .env, runtime config, and Compose project mounts."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


SENSITIVE = {"/", "/home", "/root", "/etc", "/usr", "/var", "/opt"}


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


def parse_projects(cfg: dict) -> list[dict]:
    if cfg.get("projects_dir"):
        die(
            "'projects_dir' was removed; list each project in 'projects[]' "
            "(see cind.config.example.json)"
        )

    projects_raw = cfg.get("projects")
    if not isinstance(projects_raw, list) or not projects_raw:
        die("'projects' must be a non-empty list (at least one project)")

    projects: list[dict] = []
    seen_paths: set[str] = set()
    seen_names: set[str] = set()

    for i, item in enumerate(projects_raw):
        if not isinstance(item, dict):
            die(f"projects[{i}] must be an object")
        name = str(item.get("name") or "").strip()
        path = str(item.get("path") or "").strip()
        tmux = str(item.get("tmux") or name or "").strip()
        if not name or not path:
            die(f"projects[{i}] requires name and path")
        if name in seen_names:
            die(f"duplicate project name: {name}")
        resolved = resolve_abs(path, f"projects[{i}].path")
        path_key = str(resolved)
        if path_key in seen_paths:
            die(f"duplicate project path: {path_key}")
        seen_names.add(name)
        seen_paths.add(path_key)

        windows_raw = item.get("windows") or []
        if windows_raw and not isinstance(windows_raw, list):
            die(f"projects[{i}].windows must be a list")
        windows: list[dict] = []
        for j, win in enumerate(windows_raw):
            if not isinstance(win, dict):
                die(f"projects[{i}].windows[{j}] must be an object")
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
                "tmux": tmux or name,
                "windows": windows,
            }
        )

    return projects


def resolve_default_project(projects: list[dict], default_name: str) -> Path:
    if default_name:
        for p in projects:
            if p["name"] == default_name:
                return Path(p["path"])
        die(f"default_project not found in projects[]: {default_name}")
    return Path(projects[0]["path"])


def write_compose_projects(root: Path, project_paths: list[str]) -> Path:
    runtime_dir = root / ".cind"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    compose_path = runtime_dir / "compose-projects.generated.yml"
    lines = [
        "# Generated by apply-config.py — do not edit by hand.",
        "services:",
        "  cursor:",
        "    volumes:",
    ]
    for path in project_paths:
        lines.append(f"      - {path}:{path}")
    compose_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return compose_path


def build_from_config(cfg: dict) -> dict:
    projects = parse_projects(cfg)
    default_name = str(cfg.get("default_project") or "").strip()
    default_path = resolve_default_project(projects, default_name)

    ttyd = cfg.get("ttyd") or {}
    resources = cfg.get("resources") or {}
    if not isinstance(ttyd, dict) or not isinstance(resources, dict):
        die("ttyd and resources must be objects")

    runtime = {
        "default_project": default_name or projects[0]["name"],
        "projects": projects,
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
    return {
        "runtime": runtime,
        "project_dir": str(default_path),
        "project_paths": [p["path"] for p in projects],
    }


def synthesize_from_env(project_dir: str) -> dict:
    pd = resolve_abs(project_dir, "PROJECT_DIR")
    projects = [
        {
            "name": pd.name,
            "path": str(pd),
            "tmux": pd.name,
            "windows": [],
        }
    ]
    runtime = {
        "default_project": pd.name,
        "projects": projects,
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
        "project_paths": [str(pd)],
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

    if not env_path.exists():
        if not example.exists():
            die("missing .env and .env.example")
        env_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")

    config_path = Path(args.config) if args.config else None
    if config_path is not None and not config_path.is_absolute():
        config_path = (root / config_path).resolve()

    if config_path and config_path.is_file():
        built = build_from_config(load_config(config_path))
        print(f"Applied config: {config_path}")
    else:
        project_dir = args.project_dir or os.environ.get("PROJECT_DIR") or str(root)
        built = synthesize_from_env(project_dir)
        print("No CONFIG file; synthesized single-project runtime from PROJECT_DIR")

    runtime_dir.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text(
        json.dumps(built["runtime"], indent=2) + "\n", encoding="utf-8"
    )
    compose_path = write_compose_projects(root, built["project_paths"])

    ensure_env_key(env_path, "PROJECT_DIR", built["project_dir"])
    remove_env_key(env_path, "PROJECTS_DIR")
    remove_env_key(env_path, "PROJECT_ROOTS")
    ensure_env_key(env_path, "CIND_CONFIG_HOST", str(runtime_path))
    ensure_env_key(env_path, "CIND_CONFIG", "/etc/cind/config.json")
    ensure_env_key(env_path, "CIND_COMPOSE_PROJECTS", str(compose_path))

    ttyd = built["runtime"]["ttyd"]
    resources = built["runtime"]["resources"]
    ensure_env_key(env_path, "TTYD_PORT", str(ttyd["port"]))
    ensure_env_key(env_path, "TTYD_HOST_PORT", str(ttyd["host_port"]))
    ensure_env_key(env_path, "TTYD_FONT_SIZE", str(ttyd["font_size"]))
    ensure_env_key(env_path, "CPUS", str(resources["cpus"]))
    ensure_env_key(env_path, "MEMORY", str(resources["memory"]))
    ensure_env_key(env_path, "SHM_SIZE", str(resources["shm_size"]))
    ensure_env_key(env_path, "TMPFS_SIZE", str(resources["tmpfs_size"]))

    print(f"PROJECT_DIR={built['project_dir']}")
    print(f"projects mounted: {len(built['project_paths'])}")
    for path in built["project_paths"]:
        print(f"  - {path}")
    print(f"runtime config: {runtime_path}")
    print(f"compose mounts: {compose_path}")


if __name__ == "__main__":
    main()
