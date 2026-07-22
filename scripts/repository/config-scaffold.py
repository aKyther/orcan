#!/usr/bin/env python3
"""Create or update a minimal cind.config.json from PROJECT_DIR."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "cind.config.json"


def die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def resolve_project(path: str) -> Path:
    p = Path(path)
    if "~" in str(p):
        die("PROJECT_DIR must not contain ~")
    if not p.is_absolute():
        die(f"PROJECT_DIR must be an absolute path (got: {path})")
    if not p.is_dir():
        die(f"PROJECT_DIR does not exist or is not a directory: {path}")
    return p.resolve()


def load_config(path: Path) -> dict:
    if not path.is_file():
        return {"workspaces": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(f"invalid JSON in {path}: {exc}")
    if not isinstance(data, dict):
        die(f"config root must be an object: {path}")
    data.setdefault("workspaces", [])
    if not isinstance(data["workspaces"], list):
        die("workspaces must be an array")
    return data


def find_workspace(cfg: dict, name: str) -> dict | None:
    for ws in cfg["workspaces"]:
        if isinstance(ws, dict) and ws.get("name") == name:
            return ws
    return None


def project_entry(name: str, path: str) -> dict:
    return {"name": name, "path": path}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to cind.config.json")
    parser.add_argument("--project-dir", required=True, help="Absolute host path to a repo")
    parser.add_argument(
        "--workspace",
        default="",
        help="Workspace name (default: basename of PROJECT_DIR)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing workspace or project entry",
    )
    args = parser.parse_args()

    project = resolve_project(args.project_dir)
    ws_name = (args.workspace or project.name).strip()
    if not ws_name:
        die("workspace name is empty")

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (ROOT / config_path).resolve()

    cfg = load_config(config_path)
    ws = find_workspace(cfg, ws_name)
    proj = project_entry(project.name, str(project))

    if ws is None:
        ws = {
            "name": ws_name,
            "tmux": ws_name,
            "projects": [proj],
        }
        cfg["workspaces"].append(ws)
        action = "added workspace"
    else:
        projects = ws.setdefault("projects", [])
        if not isinstance(projects, list):
            die(f"workspaces entry {ws_name} has invalid projects[]")
        existing = next(
            (i for i, item in enumerate(projects) if item.get("name") == project.name),
            None,
        )
        if existing is not None and not args.force:
            die(
                f"project {project.name!r} already in workspace {ws_name!r}; "
                "use --force to replace"
            )
        if existing is not None:
            projects[existing] = proj
            action = "updated project"
        else:
            projects.append(proj)
            action = "added project"

    config_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print(f"{action}: workspace={ws_name} project={project.name}")
    print(f"config: {config_path}")
    print("Next: make env && make path-check")


if __name__ == "__main__":
    main()
