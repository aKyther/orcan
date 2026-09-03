#!/usr/bin/env python3
"""Create or update a minimal orcan.config.json from PROJECT_DIR."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(
    __import__("os").environ.get("ORCAN_HOME")
    or Path(__file__).resolve().parents[2]
)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_io import (  # noqa: E402
    default_write_path,
    die,
    discover_config,
    dump_config,
    find_workspace,
    load_config,
)
from path_guards import PathGuardError, checked_project_dir  # noqa: E402


def resolve_project(path: str) -> Path:
    try:
        return checked_project_dir(path, must_exist=True, require_readable=False)
    except PathGuardError as exc:
        die(f"PROJECT_DIR {exc}")


def project_entry(name: str, path: str) -> dict:
    return {"name": name, "path": path}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="",
        help="Path to config (default: discover or create orcan.config.json)",
    )
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

    if args.config:
        config_path = Path(args.config)
        if not config_path.is_absolute():
            config_path = (ROOT / config_path).resolve()
    else:
        config_path = discover_config(ROOT) or default_write_path(ROOT)

    if config_path.is_file():
        cfg = load_config(config_path)
    else:
        cfg = {"workspaces": []}
    cfg.setdefault("workspaces", [])
    if not isinstance(cfg["workspaces"], list):
        die("workspaces must be an array")

    ws = find_workspace(cfg, ws_name)
    proj = project_entry(project.name, str(project))

    if ws is None:
        ws = {
            "name": ws_name,
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

    dump_config(config_path, cfg)
    print(f"{action}: workspace={ws_name} project={project.name}")
    print(f"config: {config_path}")
    print("Next: orcan sync && orcan context show")


if __name__ == "__main__":
    main()
