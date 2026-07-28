#!/usr/bin/env python3
"""Interactive wizard to create or edit orcan.config.json."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(
    os.environ.get("ORCAN_HOME") or Path(__file__).resolve().parents[2]
)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_io import (  # noqa: E402
    default_write_path,
    discover_config,
    dump_config,
    load_config,
)

SENSITIVE = {"/", "/home", "/root", "/etc", "/usr", "/var", "/opt"}
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,48}$")

DEFAULT_TMUX = {"initial_windows": 3, "window_prefix": "tab"}
DEFAULT_TTYD = {
    "port": 7681,
    "host_port": 7681,
    "font_size": 22,
    "font_family": "Menlo, Monaco, 'Courier New', monospace",
    "theme": "dark",
}


def die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def info(msg: str) -> None:
    print(msg)


def warn(msg: str) -> None:
    print(f"Warning: {msg}", file=sys.stderr)


def ask(prompt: str, default: str | None = None) -> str:
    if default is not None and default != "":
        suffix = f" [{default}]"
    else:
        suffix = ""
    try:
        raw = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        print()
        die("cancelled (EOF)")
    if not raw and default is not None:
        return default
    return raw


def ask_yes_no(prompt: str, *, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        raw = ask(f"{prompt} ({hint})", "y" if default else "n").lower()
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        warn("Please answer y or n.")


def ask_choice(prompt: str, choices: list[str], *, default: str) -> str:
    labels = "/".join(
        c.upper() if c == default else c for c in choices
    )
    while True:
        raw = ask(f"{prompt} ({labels})", default).lower()
        for c in choices:
            if raw == c or raw == c[0]:
                return c
        warn(f"Choose one of: {', '.join(choices)}")


def validate_name(name: str, *, label: str) -> str | None:
    name = name.strip()
    if not name:
        return f"{label} cannot be empty"
    if not NAME_RE.match(name):
        return (
            f"{label} must match {NAME_RE.pattern} "
            "(letters, digits, _ and -; start with alphanumeric)"
        )
    return None


def validate_project_path(path_str: str) -> tuple[str | None, Path | None]:
    path_str = path_str.strip()
    if not path_str:
        return "path cannot be empty", None
    if "~" in path_str:
        return "path must not contain ~ (use an absolute path)", None
    p = Path(path_str)
    if not p.is_absolute():
        return f"path must be absolute (got: {path_str})", None
    if not p.exists():
        return f"path does not exist: {path_str}", None
    if not p.is_dir():
        return f"path is not a directory: {path_str}", None
    try:
        resolved = p.resolve()
    except OSError as exc:
        return f"cannot resolve path: {exc}", None
    if str(resolved) in SENSITIVE:
        return f"refusing sensitive path: {resolved}", None
    home = Path.home().resolve()
    if resolved == home:
        return f"refusing to mount entire home: {resolved}", None
    if not os.access(resolved, os.R_OK):
        return f"path is not readable: {resolved}", None
    return None, resolved


def ask_name(prompt: str, *, default: str = "", label: str = "name") -> str:
    while True:
        raw = ask(prompt, default or None)
        err = validate_name(raw, label=label)
        if err:
            warn(err)
            continue
        return raw.strip()


def ask_project_path(prompt: str, *, default: str = "") -> str:
    while True:
        raw = ask(prompt, default or None)
        err, resolved = validate_project_path(raw)
        if err:
            warn(err)
            if not ask_yes_no("Try again?", default=True):
                die("cancelled")
            continue
        assert resolved is not None
        return str(resolved)


def ask_project(*, default_name: str = "", default_path: str = "") -> dict[str, str]:
    name = ask_name("  Project name", default=default_name, label="project name")
    path = ask_project_path("  Project path (absolute)", default=default_path)
    basename = Path(path).name
    if basename != name:
        # User-chosen name wins; only switch if they explicitly decline to keep it.
        keep = ask_yes_no(
            f"  Keep project name {name!r}? (folder is {basename!r})",
            default=True,
        )
        if not keep:
            err = validate_name(basename, label="project name")
            if err:
                warn(f"{err} — keeping {name!r}")
            else:
                info(f"  Using folder name {basename!r} as project name.")
                name = basename
    return {"name": name, "path": path}


def ask_new_workspace(*, prompt_confirm: bool = False) -> dict[str, Any] | None:
    """Collect one workspace. Skip confirm when the caller already asked."""
    if prompt_confirm and not ask_yes_no("Create a workspace?", default=True):
        return None
    name = ask_name("Workspace name", label="workspace name")
    projects: list[dict[str, str]] = []
    info(f"Add at least one project to workspace {name!r}.")
    while True:
        if projects:
            if not ask_yes_no(
                f"Add another project to workspace {name!r}?",
                default=False,
            ):
                break
        projects.append(ask_project())
    return {"name": name, "projects": projects}


def summarize(cfg: dict[str, Any]) -> None:
    workspaces = cfg.get("workspaces") or []
    info("")
    info("Current config:")
    if not workspaces:
        info("  (no workspaces)")
        return
    for i, ws in enumerate(workspaces, 1):
        if not isinstance(ws, dict):
            continue
        info(f"  {i}. workspace {ws.get('name', '?')}")
        for p in ws.get("projects") or []:
            if isinstance(p, dict):
                info(f"       - {p.get('name')}: {p.get('path')}")


def edit_project(proj: dict[str, Any]) -> dict[str, Any] | None:
    info(f"  Project: {proj.get('name')} @ {proj.get('path')}")
    action = ask_choice("  Keep, change, or delete this project?", ["keep", "change", "delete"], default="keep")
    if action == "keep":
        return dict(proj)
    if action == "delete":
        return None
    return ask_project(
        default_name=str(proj.get("name") or ""),
        default_path=str(proj.get("path") or ""),
    )


def ask_more_projects(name: str, projects: list[dict[str, str]]) -> list[dict[str, str]]:
    """Prompt to append projects while staying in the same workspace."""
    while ask_yes_no(f"Add another project to workspace {name!r}?", default=False):
        projects.append(ask_project())
    return projects


def edit_workspace(ws: dict[str, Any]) -> dict[str, Any] | None:
    info(f"Workspace: {ws.get('name')}")
    action = ask_choice(
        "Keep, change, or delete this workspace?",
        ["keep", "change", "delete"],
        default="keep",
    )
    if action == "delete":
        return None

    if action == "keep":
        name = str(ws.get("name") or "")
        projects_out = [
            dict(p) for p in (ws.get("projects") or []) if isinstance(p, dict)
        ]
        ask_more_projects(name, projects_out)
        return {"name": name, "projects": projects_out}

    name = ask_name(
        "Workspace name",
        default=str(ws.get("name") or ""),
        label="workspace name",
    )
    projects_out: list[dict[str, str]] = []
    for proj in ws.get("projects") or []:
        if not isinstance(proj, dict):
            continue
        edited = edit_project(proj)
        if edited is not None:
            projects_out.append(edited)
    ask_more_projects(name, projects_out)
    if not projects_out:
        warn("Workspace must have at least one project.")
        if ask_yes_no("Add a project now?", default=True):
            projects_out.append(ask_project())
            ask_more_projects(name, projects_out)
        else:
            warn("Dropping empty workspace.")
            return None
    return {"name": name, "projects": projects_out}


def edit_existing(cfg: dict[str, Any]) -> dict[str, Any]:
    summarize(cfg)
    info("")
    info("Review each workspace (keep / change / delete).")
    new_workspaces: list[dict[str, Any]] = []
    for ws in cfg.get("workspaces") or []:
        if not isinstance(ws, dict):
            continue
        edited = edit_workspace(ws)
        if edited is not None:
            new_workspaces.append(edited)
    while ask_yes_no("Add another workspace?", default=False):
        created = ask_new_workspace(prompt_confirm=False)
        if created:
            new_workspaces.append(created)
    if not new_workspaces:
        die("config must contain at least one workspace — nothing saved")
    out = dict(cfg)
    out["workspaces"] = new_workspaces
    return out


def create_fresh() -> dict[str, Any]:
    info("No orcan config found — building a new orcan.config.json")
    workspaces: list[dict[str, Any]] = []
    while True:
        # First workspace is implied; later ones already confirmed by
        # "Add another workspace?" — never re-ask "Create a workspace?".
        label = "first" if not workspaces else "next"
        info(f"\nConfigure the {label} workspace.")
        created = ask_new_workspace(prompt_confirm=False)
        if created:
            workspaces.append(created)
        elif not workspaces:
            warn("You need at least one workspace.")
            if not ask_yes_no("Try again?", default=True):
                die("cancelled")
            continue
        if not ask_yes_no("Add another workspace?", default=False):
            break
    cfg: dict[str, Any] = {"workspaces": workspaces}
    if ask_yes_no("Configure tmux defaults (windows / prefix)?", default=False):
        windows = ask("Initial tmux windows per workspace", "3")
        try:
            n = int(windows)
            if n < 1:
                n = 1
            if n > 9:
                n = 9
        except ValueError:
            n = 3
            warn("Invalid number — using 3")
        prefix = ask("Window name prefix", "tab") or "tab"
        cfg["tmux"] = {"initial_windows": n, "window_prefix": prefix}
    else:
        cfg["tmux"] = dict(DEFAULT_TMUX)
    if ask_yes_no("Configure ttyd (port / font)?", default=False):
        port = ask("ttyd container port", "7681")
        host_port = ask("ttyd host port", port)
        font = ask("ttyd font size", "22")
        try:
            cfg["ttyd"] = {
                "port": int(port),
                "host_port": int(host_port),
                "font_size": int(font),
                "font_family": DEFAULT_TTYD["font_family"],
                "theme": DEFAULT_TTYD["theme"],
            }
        except ValueError:
            warn("Invalid ttyd numbers — using defaults")
            cfg["ttyd"] = dict(DEFAULT_TTYD)
    else:
        cfg["ttyd"] = dict(DEFAULT_TTYD)
    return cfg


def ensure_unique_names(cfg: dict[str, Any]) -> None:
    seen_ws: set[str] = set()
    for ws in cfg.get("workspaces") or []:
        if not isinstance(ws, dict):
            continue
        name = str(ws.get("name") or "")
        if name in seen_ws:
            die(f"duplicate workspace name: {name}")
        seen_ws.add(name)
        seen_proj: set[str] = set()
        seen_path: set[str] = set()
        for p in ws.get("projects") or []:
            if not isinstance(p, dict):
                continue
            pn = str(p.get("name") or "")
            pp = str(p.get("path") or "")
            if pn in seen_proj:
                die(f"duplicate project name in workspace {name}: {pn}")
            if pp in seen_path:
                die(f"duplicate project path in workspace {name}: {pp}")
            seen_proj.add(pn)
            seen_path.add(pp)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=str(ROOT),
        help="Repository root (default: orcan repo)",
    )
    parser.add_argument(
        "--config",
        default="",
        help="Config path (default: discover or create orcan.config.json)",
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()

    if not sys.stdin.isatty():
        die("config wizard needs an interactive TTY (run in a terminal)")

    info("orcan config wizard")
    info("──────────────────")

    if args.config:
        existing = Path(args.config)
        if not existing.is_absolute():
            existing = (root / existing).resolve()
        if not existing.is_file():
            die(f"config not found: {existing}")
    else:
        found = discover_config(root)
        existing = found

    if existing and existing.is_file():
        info(f"Found: {existing}")
        cfg = load_config(existing)
        if not ask_yes_no("Edit this config interactively?", default=True):
            info("Cancelled — no changes.")
            return
        cfg = edit_existing(cfg)
        out_path = existing
    else:
        cfg = create_fresh()
        out_path = default_write_path(root)

    ensure_unique_names(cfg)
    summarize(cfg)
    info("")
    if not ask_yes_no(f"Write {out_path}?", default=True):
        info("Cancelled — nothing written.")
        return

    dump_config(out_path, cfg)
    info(f"Wrote {out_path}")
    info("Next: orcan sync")
    info("      orcan up")


if __name__ == "__main__":
    main()
