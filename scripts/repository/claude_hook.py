#!/usr/bin/env python3
"""Toggle the optional Claude Code Stop hook (orcan-context-reflect) in a
project's .claude/settings.json. Host-side, stdlib only — writes directly
into the git checkout (path-parity means the host path is the container
path), no container round-trip needed. See docs/en/ideas/context-assertions.md
("Batched, automated Reflection").
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_io import load_config  # noqa: E402

HOOK_COMMAND = "orcan-context-reflect"
HOOK_ENTRY = {"hooks": [{"type": "command", "command": HOOK_COMMAND, "async": True}]}


def die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def settings_path(project: Path) -> Path:
    return project / ".claude" / "settings.json"


def load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        die(f"invalid JSON in {path}: {exc}")
    if not isinstance(data, dict):
        die(f"settings root must be an object: {path}")
    return data


def has_hook(settings: dict[str, Any]) -> bool:
    stop = settings.get("hooks", {}).get("Stop", [])
    return any(
        h.get("command") == HOOK_COMMAND
        for entry in stop
        for h in entry.get("hooks", [])
    )


def backup(path: Path) -> None:
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = path.with_name(f"{path.name}.bak.{stamp}")
    dest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")


def write_settings(path: Path, settings: dict[str, Any]) -> None:
    if path.exists():
        backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def enable(project: Path, *, dry_run: bool) -> str:
    path = settings_path(project)
    settings = load_settings(path)
    if has_hook(settings):
        return "already enabled"
    if dry_run:
        return "would enable"
    settings.setdefault("hooks", {}).setdefault("Stop", []).append(HOOK_ENTRY)
    write_settings(path, settings)
    return "enabled"


def disable(project: Path, *, dry_run: bool) -> str:
    path = settings_path(project)
    if not path.exists():
        return "already disabled"
    settings = load_settings(path)
    if not has_hook(settings):
        return "already disabled"
    if dry_run:
        return "would disable"
    stop = [
        entry
        for entry in settings["hooks"]["Stop"]
        if not any(h.get("command") == HOOK_COMMAND for h in entry.get("hooks", []))
    ]
    if stop:
        settings["hooks"]["Stop"] = stop
    else:
        del settings["hooks"]["Stop"]
    if not settings["hooks"]:
        del settings["hooks"]
    write_settings(path, settings)
    return "disabled"


def status(project: Path) -> str:
    return "enabled" if has_hook(load_settings(settings_path(project))) else "disabled"


def project_paths_from_config(config_path: Path) -> list[Path]:
    if not config_path.is_file():
        die(f"config not found: {config_path}")
    cfg = load_config(config_path)
    paths: list[Path] = []
    for ws in cfg.get("workspaces", []):
        for proj in ws.get("projects", []):
            p = proj.get("path")
            if p:
                paths.append(Path(p))
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["enable", "disable", "status"])
    parser.add_argument(
        "paths", nargs="*", type=Path, help="Project directories (default: cwd)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Apply to every project path in --config",
    )
    parser.add_argument(
        "--config", type=Path, default=None, help="orcan.config.json (for --all)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would change, write nothing"
    )
    args = parser.parse_args()

    if args.all:
        if args.paths:
            die("use either explicit paths or --all, not both")
        if args.config is None:
            die("--all needs --config")
        targets = project_paths_from_config(args.config)
    else:
        targets = args.paths or [Path.cwd()]

    fail = 0
    for target in targets:
        target = target.resolve()
        if not target.is_dir():
            print(f"Skip (missing dir): {target}", file=sys.stderr)
            fail = 1
            continue
        if args.action == "enable":
            result = enable(target, dry_run=args.dry_run)
        elif args.action == "disable":
            result = disable(target, dry_run=args.dry_run)
        else:
            result = status(target)
        print(f"{result:<15} {target}")

    return fail


if __name__ == "__main__":
    raise SystemExit(main())
