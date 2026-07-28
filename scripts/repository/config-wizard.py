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


def info(msg: str = "") -> None:
    print(msg)


def warn(msg: str) -> None:
    print(f"  ! {msg}", file=sys.stderr)


def step(num: int, title: str) -> None:
    info()
    info(f"── {num}. {title} ──")


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
        warn("answer y or n")


def ask_choice(prompt: str, choices: list[str], *, default: str) -> str:
    labels = "/".join(c.upper() if c == default else c for c in choices)
    while True:
        raw = ask(f"{prompt} ({labels})", default).lower()
        for c in choices:
            if raw == c or raw == c[0]:
                return c
        warn(f"choose: {', '.join(choices)}")


def validate_name(name: str, *, label: str) -> str | None:
    name = name.strip()
    if not name:
        return f"{label} cannot be empty"
    if not NAME_RE.match(name):
        return (
            f"{label}: letters, digits, _ and - only "
            "(must start with alphanumeric)"
        )
    return None


def validate_project_path(path_str: str) -> tuple[str | None, Path | None]:
    path_str = path_str.strip()
    if not path_str:
        return "path cannot be empty", None
    if "~" in path_str:
        return "use an absolute path (no ~)", None
    p = Path(path_str)
    if not p.is_absolute():
        return f"path must be absolute (got: {path_str})", None
    if not p.exists():
        return f"does not exist: {path_str}", None
    if not p.is_dir():
        return f"not a directory: {path_str}", None
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
        return f"not readable: {resolved}", None
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
            continue
        assert resolved is not None
        return str(resolved)


def ask_project(
    *,
    default_name: str = "",
    default_path: str = "",
    index: int | None = None,
) -> dict[str, str]:
    prefix = f"  [{index}] " if index is not None else "  "
    name = ask_name(
        f"{prefix}Project name",
        default=default_name,
        label="project name",
    )
    path = ask_project_path(
        f"{prefix}Project path (absolute)",
        default=default_path,
    )
    basename = Path(path).name
    if basename != name:
        keep = ask_yes_no(
            f"{prefix}Keep name {name!r}? (folder is {basename!r})",
            default=True,
        )
        if not keep:
            err = validate_name(basename, label="project name")
            if err:
                warn(f"{err} — keeping {name!r}")
            else:
                info(f"{prefix}Using folder name {basename!r}.")
                name = basename
    return {"name": name, "path": path}


def ask_new_workspace(*, index: int | None = None) -> dict[str, Any]:
    """Collect one workspace (caller already decided to add it)."""
    if index is not None:
        info(f"Workspace {index}")
    name = ask_name("  Workspace name", label="workspace name")
    projects: list[dict[str, str]] = []
    info(f"  Add projects for {name!r} (at least one).")
    while True:
        n = len(projects) + 1
        if projects and not ask_yes_no(
            f"  Add another project to {name!r}?",
            default=False,
        ):
            break
        projects.append(ask_project(index=n))
    info(f"  ✓ workspace {name!r}: {len(projects)} project(s)")
    return {"name": name, "projects": projects}


def summarize(cfg: dict[str, Any], *, title: str = "Summary") -> None:
    workspaces = cfg.get("workspaces") or []
    info()
    info(f"── {title} ──")
    if not workspaces:
        info("  (no workspaces)")
        return
    for i, ws in enumerate(workspaces, 1):
        if not isinstance(ws, dict):
            continue
        info(f"  {i}. {ws.get('name', '?')}")
        for p in ws.get("projects") or []:
            if isinstance(p, dict):
                info(f"       • {p.get('name')}  →  {p.get('path')}")
    tmux = cfg.get("tmux") if isinstance(cfg.get("tmux"), dict) else None
    ttyd = cfg.get("ttyd") if isinstance(cfg.get("ttyd"), dict) else None
    if tmux:
        info(
            f"  tmux: {tmux.get('initial_windows', '?')} windows, "
            f"prefix {tmux.get('window_prefix', '?')!r}"
        )
    if ttyd:
        info(
            f"  ttyd: host port {ttyd.get('host_port', '?')}, "
            f"font {ttyd.get('font_size', '?')}"
        )


def edit_project(proj: dict[str, Any], *, index: int) -> dict[str, Any] | None:
    info(f"  [{index}] {proj.get('name')}  →  {proj.get('path')}")
    action = ask_choice(
        "      Action",
        ["keep", "change", "delete"],
        default="keep",
    )
    if action == "keep":
        return dict(proj)
    if action == "delete":
        return None
    return ask_project(
        default_name=str(proj.get("name") or ""),
        default_path=str(proj.get("path") or ""),
        index=index,
    )


def ask_more_projects(name: str, projects: list[dict[str, str]]) -> list[dict[str, str]]:
    while ask_yes_no(f"  Add another project to {name!r}?", default=False):
        projects.append(ask_project(index=len(projects) + 1))
    return projects


def edit_workspace(ws: dict[str, Any], *, index: int) -> dict[str, Any] | None:
    info()
    info(f"Workspace {index}: {ws.get('name')}")
    action = ask_choice(
        "  Action",
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
        "  Workspace name",
        default=str(ws.get("name") or ""),
        label="workspace name",
    )
    projects_out: list[dict[str, str]] = []
    for i, proj in enumerate(ws.get("projects") or [], 1):
        if not isinstance(proj, dict):
            continue
        edited = edit_project(proj, index=i)
        if edited is not None:
            projects_out.append(edited)
    ask_more_projects(name, projects_out)
    if not projects_out:
        warn("workspace needs at least one project")
        if ask_yes_no("  Add a project now?", default=True):
            projects_out.append(ask_project(index=1))
            ask_more_projects(name, projects_out)
        else:
            warn("dropping empty workspace")
            return None
    return {"name": name, "projects": projects_out}


def edit_existing(cfg: dict[str, Any]) -> dict[str, Any]:
    summarize(cfg, title="Current config")
    step(1, "Review workspaces")
    info("For each: keep (Enter), change, or delete.")
    new_workspaces: list[dict[str, Any]] = []
    for i, ws in enumerate(cfg.get("workspaces") or [], 1):
        if not isinstance(ws, dict):
            continue
        edited = edit_workspace(ws, index=i)
        if edited is not None:
            new_workspaces.append(edited)
    step(2, "More workspaces?")
    while ask_yes_no("Add another workspace?", default=False):
        created = ask_new_workspace(index=len(new_workspaces) + 1)
        new_workspaces.append(created)
    if not new_workspaces:
        die("need at least one workspace — nothing saved")
    out = dict(cfg)
    out["workspaces"] = new_workspaces
    return out


def ask_optional_settings(cfg: dict[str, Any]) -> None:
    step(2, "Optional settings")
    info("Defaults are fine for most people (tmux + browser terminal).")
    if not ask_yes_no("Customize tmux or ttyd?", default=False):
        cfg["tmux"] = dict(DEFAULT_TMUX)
        cfg["ttyd"] = dict(DEFAULT_TTYD)
        info("  Using defaults (3 tmux windows, ttyd port 7681).")
        return

    if ask_yes_no("  Change tmux (windows / prefix)?", default=False):
        windows = ask("  Initial tmux windows per workspace", "3")
        try:
            n = int(windows)
            n = max(1, min(9, n))
        except ValueError:
            n = 3
            warn("invalid number — using 3")
        prefix = ask("  Window name prefix", "tab") or "tab"
        cfg["tmux"] = {"initial_windows": n, "window_prefix": prefix}
    else:
        cfg["tmux"] = dict(DEFAULT_TMUX)

    if ask_yes_no("  Change ttyd (port / font)?", default=False):
        port = ask("  ttyd container port", "7681")
        host_port = ask("  ttyd host port", port)
        font = ask("  ttyd font size", "22")
        try:
            cfg["ttyd"] = {
                "port": int(port),
                "host_port": int(host_port),
                "font_size": int(font),
                "font_family": DEFAULT_TTYD["font_family"],
                "theme": DEFAULT_TTYD["theme"],
            }
        except ValueError:
            warn("invalid ttyd numbers — using defaults")
            cfg["ttyd"] = dict(DEFAULT_TTYD)
    else:
        cfg["ttyd"] = dict(DEFAULT_TTYD)


def create_fresh() -> dict[str, Any]:
    info("No config yet — let's create orcan.config.json")
    step(1, "Workspaces")
    info("A workspace is a named set of project folders (one tmux session).")
    workspaces: list[dict[str, Any]] = []
    while True:
        created = ask_new_workspace(index=len(workspaces) + 1)
        workspaces.append(created)
        if not ask_yes_no("Add another workspace?", default=False):
            break
    cfg: dict[str, Any] = {"workspaces": workspaces}
    ask_optional_settings(cfg)
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
        help="ORCAN_HOME / repo root (default: ORCAN_HOME or orcan repo)",
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
    info("───────────────────")

    if args.config:
        existing = Path(args.config)
        if not existing.is_absolute():
            existing = (root / existing).resolve()
        if not existing.is_file():
            die(f"config not found: {existing}")
    else:
        existing = discover_config(root)

    if existing and existing.is_file():
        info(f"Config: {existing}")
        cfg = load_config(existing)
        if not ask_yes_no("Edit this config?", default=True):
            info("Cancelled — no changes.")
            return
        cfg = edit_existing(cfg)
        out_path = existing
    else:
        cfg = create_fresh()
        out_path = default_write_path(root)

    ensure_unique_names(cfg)
    summarize(cfg, title="Review before save")
    info()
    info(f"Will write: {out_path}")
    if not ask_yes_no("Save?", default=True):
        info("Cancelled — nothing written.")
        return

    dump_config(out_path, cfg)
    info()
    info(f"Saved {out_path}")
    info("Next:")
    info("  orcan sync")
    info("  orcan up")


if __name__ == "__main__":
    main()
