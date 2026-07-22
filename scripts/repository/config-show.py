#!/usr/bin/env python3
"""Print workspaces from cind.config.json or generated runtime manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(f"invalid JSON in {path}: {exc}")
    if not isinstance(data, dict):
        die(f"expected object in {path}")
    return data


def print_workspaces(title: str, workspaces: list) -> None:
    print(title)
    if not workspaces:
        print("  (none)")
        return
    for i, ws in enumerate(workspaces, 1):
        if not isinstance(ws, dict):
            continue
        name = ws.get("name", "?")
        root = ws.get("root", "")
        projects = ws.get("projects") or []
        root_suffix = f" @ {root}" if root else ""
        print(f"  {i}. {name}{root_suffix}")
        print(f"     projects={len(projects)}")
        for p in projects:
            if not isinstance(p, dict):
                continue
            symlink = p.get("workspace_path") or ""
            suffix = f" → {symlink}" if symlink else ""
            print(f"       - {p.get('name')}: {p.get('path')}{suffix}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(ROOT / "cind.config.json"),
        help="Source cind.config.json",
    )
    parser.add_argument(
        "--runtime",
        default=str(ROOT / ".cind" / "workspace.manifest.json"),
        help="Generated manifest from make env",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    runtime_path = Path(args.runtime)

    if config_path.is_file():
        cfg = load_json(config_path)
        print_workspaces(f"Config: {config_path}", cfg.get("workspaces") or [])
        print()
    else:
        print(f"Config: {config_path} (missing — run make config-init)\n")

    if runtime_path.is_file():
        manifest = load_json(runtime_path)
        print_workspaces(f"Runtime: {runtime_path}", manifest.get("workspaces") or [])
    else:
        print(f"Runtime: {runtime_path} (missing — run make env)")


if __name__ == "__main__":
    main()
