#!/usr/bin/env python3
"""Toggle the Claude Code Stop hook (orcan-context-reflect) in a workspace's
generated root .claude/settings.json — the directory Claude Code sessions
actually launch in (tmux windows always start at the workspace root, never
inside a project checkout; see cursor-tmux-workspace-attach). On by default:
apply-config.py seeds it the first time a workspace is synced (no existing
.claude/settings.json yet); this module's `enable`/`disable` are what make
opting *out* configurable — once toggled, a workspace's `.claude/settings.json`
already exists, so later syncs never touch the hook again. Host-side, stdlib
only — writes directly into the generated workspace meta dir (path-parity
means the host path is the container path), no container round-trip needed.
Targets are resolved by workspace name via the manifest `orcan sync` writes
(<ORCAN_HOME>/workspaces/index.json), so a workspace must have been synced at
least once before its hook can be toggled. See
docs/en/ideas/context-assertions.md ("Batched, automated Reflection").
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Any

HOOK_COMMAND = "orcan-context-reflect"
HOOK_ENTRY = {"hooks": [{"type": "command", "command": HOOK_COMMAND, "async": True}]}


def die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def settings_path(target_dir: Path) -> Path:
    return target_dir / ".claude" / "settings.json"


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


def enable(target_dir: Path, *, dry_run: bool) -> str:
    path = settings_path(target_dir)
    settings = load_settings(path)
    if has_hook(settings):
        return "already enabled"
    if dry_run:
        return "would enable"
    settings.setdefault("hooks", {}).setdefault("Stop", []).append(HOOK_ENTRY)
    write_settings(path, settings)
    return "enabled"


def disable(target_dir: Path, *, dry_run: bool) -> str:
    path = settings_path(target_dir)
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


def status(target_dir: Path) -> str:
    return "enabled" if has_hook(load_settings(settings_path(target_dir))) else "disabled"


def load_manifest(home: Path) -> dict[str, Any]:
    path = home / "workspaces" / "index.json"
    if not path.is_file():
        die(f"workspace manifest not found: {path} (run: orcan sync)")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(f"invalid JSON in {path}: {exc}")
    if not isinstance(data, dict):
        die(f"manifest root must be an object: {path}")
    return data


def workspace_meta_paths(
    home: Path, names: list[str] | None = None
) -> list[tuple[str, Path]]:
    manifest = load_manifest(home)
    workspaces = [
        w for w in manifest.get("workspaces", []) if isinstance(w, dict) and w.get("name")
    ]
    by_name = {w["name"]: w for w in workspaces}
    if names:
        missing = [n for n in names if n not in by_name]
        if missing:
            known = ", ".join(sorted(by_name)) or "none"
            die(f"unknown workspace(s): {', '.join(missing)} (known: {known})")
        selected = [by_name[n] for n in names]
    else:
        selected = workspaces
    return [(w["name"], Path(w["meta_path"])) for w in selected if w.get("meta_path")]


def infer_workspace_from_cwd(home: Path, cwd: Path) -> str | None:
    """Which workspace (if any) owns a registered project containing cwd."""
    manifest = load_manifest(home)
    cwd = cwd.resolve()
    for ws in manifest.get("workspaces", []):
        if not isinstance(ws, dict):
            continue
        for proj in ws.get("projects") or []:
            p = proj.get("path") if isinstance(proj, dict) else None
            if not p:
                continue
            try:
                anchor = Path(p).resolve()
            except OSError:
                continue
            if cwd == anchor or anchor in cwd.parents:
                return ws.get("name")
    return None


def resolve_default_targets(home: Path, *, action: str) -> list[tuple[str, Path]]:
    """Targets when no WORKSPACE name(s) and no --all were given on the CLI.

    Prefers the workspace that owns whatever registered project cwd is
    inside of — so running this from a project checkout scopes to *that*
    project's workspace, not some unrelated default. When cwd matches
    nothing, `status` (read-only) falls back to showing every workspace —
    but says so explicitly, so it never reads as a status *for* cwd.
    """
    cwd = Path.cwd()
    inferred = infer_workspace_from_cwd(home, cwd)
    if inferred is not None:
        return workspace_meta_paths(home, [inferred])

    all_targets = workspace_meta_paths(home)
    if len(all_targets) <= 1:
        return all_targets

    if action != "status":
        die(
            f"{cwd} is not inside any registered project, and multiple "
            "workspaces are configured — specify name(s) or --all"
        )

    names = ", ".join(name for name, _ in all_targets)
    print(
        f"Note: {cwd} is not inside any registered project — not tied to one "
        f"workspace. Showing every configured workspace ({names}).",
    )
    return all_targets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["enable", "disable", "status"])
    parser.add_argument(
        "names",
        nargs="*",
        help="Workspace name(s) (default: every workspace for status; "
        "the only configured one for enable/disable)",
    )
    parser.add_argument(
        "--all", action="store_true", help="Apply to every workspace in --home"
    )
    parser.add_argument(
        "--home",
        type=Path,
        required=True,
        help="ORCAN_HOME (reads workspaces/index.json)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would change, write nothing"
    )
    args = parser.parse_args()

    if args.all and args.names:
        die("use either explicit workspace name(s) or --all, not both")

    if args.names:
        targets = workspace_meta_paths(args.home, args.names)
    elif args.all:
        targets = workspace_meta_paths(args.home)
    else:
        targets = resolve_default_targets(args.home, action=args.action)

    fail = 0
    for name, target in targets:
        target = target.resolve()
        if not target.is_dir():
            print(f"Skip (missing dir): {name} ({target})", file=sys.stderr)
            fail = 1
            continue
        if args.action == "enable":
            result = enable(target, dry_run=args.dry_run)
        elif args.action == "disable":
            result = disable(target, dry_run=args.dry_run)
        else:
            result = status(target)
        print(f"{result:<15} {name:<20} {target}")

    return fail


if __name__ == "__main__":
    raise SystemExit(main())
