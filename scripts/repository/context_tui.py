#!/usr/bin/env python3
"""Terminal UI to build a workspace from a parent directory of repos.

Flow:
  1. Point at a parent folder
  2. Multi-select git repos inside it
  3. Name the workspace
  4. Optional: one branch → managed worktree per selected repo
  5. Write orcan.config.json (then caller may sync)

Stdlib only (curses). Non-interactive flags exist for scripts/tests.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("ORCAN_HOME") or Path(__file__).resolve().parents[2])
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_io import (  # noqa: E402
    default_write_path,
    discover_config,
    dump_config,
    load_config,
)
from git_worktrees import is_git_repo, safe_segment  # noqa: E402
from managed_workspace import create_managed_workspace, find_workspace  # noqa: E402

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,48}$")
STATE_NAME = "context-tui-state.json"


def die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def info(msg: str = "") -> None:
    print(msg)


def state_path() -> Path:
    return ROOT / ".orcan" / STATE_NAME


def load_state() -> dict[str, Any]:
    path = state_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(data: dict[str, Any]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def scan_repos(parent: Path, *, max_depth: int = 2) -> list[Path]:
    """Find git repos under parent (depth 1 = children, 2 = grandchildren)."""
    parent = parent.expanduser().resolve()
    if not parent.is_dir():
        die(f"not a directory: {parent}")

    found: list[Path] = []
    seen: set[Path] = set()

    def consider(path: Path) -> None:
        try:
            resolved = path.resolve()
        except OSError:
            return
        if resolved in seen or not resolved.is_dir():
            return
        if is_git_repo(resolved):
            seen.add(resolved)
            found.append(resolved)

    # Parent itself may be a monorepo root
    consider(parent)

    try:
        children = sorted(
            (p for p in parent.iterdir() if p.is_dir() and not p.name.startswith(".")),
            key=lambda p: p.name.lower(),
        )
    except OSError as exc:
        die(f"cannot list {parent}: {exc}")

    for child in children:
        consider(child)
        if max_depth < 2:
            continue
        if is_git_repo(child):
            continue
        try:
            grand = sorted(
                (p for p in child.iterdir() if p.is_dir() and not p.name.startswith(".")),
                key=lambda p: p.name.lower(),
            )
        except OSError:
            continue
        for g in grand:
            consider(g)

    # Prefer nested repos over listing the parent when parent is not the only hit
    if len(found) > 1 and parent.resolve() in found and is_git_repo(parent):
        # Keep parent only if it is the sole repo; else drop it so multi-project
        # folders (many child repos) stay the focus.
        only_children = [p for p in found if p != parent.resolve()]
        if only_children:
            found = only_children

    return found


def resolve_config(path: str) -> Path:
    if path:
        p = Path(path)
        if not p.is_absolute():
            p = (ROOT / p).resolve()
        return p
    return discover_config(ROOT) or default_write_path(ROOT)


def default_workspace_name(parent: Path) -> str:
    name = parent.name.strip() or "workspace"
    if NAME_RE.match(name):
        return name
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-_")
    return cleaned[:48] or "workspace"


def apply_selection(
    *,
    config_path: Path,
    workspace: str,
    repos: list[Path],
    branch: str | None,
    force: bool = False,
    start_point: str = "HEAD",
) -> dict[str, Any]:
    """Write config. If branch is set, create managed worktrees; else mount paths."""
    if not repos:
        die("no repositories selected")
    ws_name = safe_segment(workspace, label="workspace")

    projects: list[tuple[str, Path]] = []
    used_names: set[str] = set()
    for repo in repos:
        base = safe_segment(repo.name, label="project")
        name = base
        n = 2
        while name in used_names:
            name = f"{base}-{n}"
            n += 1
        used_names.add(name)
        projects.append((name, repo))

    if branch:
        from git_worktrees import create_worktree

        branch_s = branch.strip()
        if not branch_s:
            die("branch is empty")

        if config_path.is_file():
            cfg = load_config(config_path)
        else:
            cfg = {"workspaces": []}
        cfg.setdefault("workspaces", [])
        if not isinstance(cfg["workspaces"], list):
            die("workspaces must be an array")

        existing = find_workspace(cfg, ws_name)
        if existing is None:
            return create_managed_workspace(
                config_path=config_path,
                workspace=ws_name,
                branch=branch_s,
                projects=projects,
                start_point=start_point,
                force=force,
            )

        # Append into an existing workspace (dokładanie projektów).
        plist = existing.setdefault("projects", [])
        if not isinstance(plist, list):
            die(f"workspace {ws_name!r} has invalid projects[]")
        by_name = {
            str(p.get("name")): i
            for i, p in enumerate(plist)
            if isinstance(p, dict) and p.get("name")
        }
        added = 0
        for proj_name, repo in projects:
            info(f"  worktree: {proj_name} ← {repo} @ {branch_s}")
            wt = create_worktree(
                repo,
                branch=branch_s,
                start_point=start_point,
                workspace=ws_name,
                project=proj_name,
                managed=True,
            )
            entry = {"name": proj_name, "path": str(wt.path)}
            idx = by_name.get(proj_name)
            if idx is not None:
                if not force:
                    die(
                        f"project {proj_name!r} already in workspace {ws_name!r}; "
                        "use --force to replace"
                    )
                plist[idx] = entry
            else:
                plist.append(entry)
                added += 1
        dump_config(config_path, cfg)
        info(f"updated workspace {ws_name!r} (+{added} managed worktree(s))")
        info(f"config: {config_path}")
        info("Next: orcan sync && orcan down && orcan up")
        return cfg

    # Mount as-is (append or create workspace).
    if config_path.is_file():
        cfg = load_config(config_path)
    else:
        cfg = {"workspaces": []}
    cfg.setdefault("workspaces", [])
    if not isinstance(cfg["workspaces"], list):
        die("workspaces must be an array")

    existing = find_workspace(cfg, ws_name)
    entries = [{"name": n, "path": str(p)} for n, p in projects]

    if existing is None:
        cfg["workspaces"].append({"name": ws_name, "projects": entries})
        info(f"created workspace {ws_name!r} with {len(entries)} project(s)")
    else:
        plist = existing.setdefault("projects", [])
        if not isinstance(plist, list):
            die(f"workspace {ws_name!r} has invalid projects[]")
        by_name = {
            str(p.get("name")): i
            for i, p in enumerate(plist)
            if isinstance(p, dict) and p.get("name")
        }
        for entry in entries:
            idx = by_name.get(entry["name"])
            if idx is not None:
                if not force:
                    die(
                        f"project {entry['name']!r} already in workspace {ws_name!r}; "
                        "use --force to replace"
                    )
                plist[idx] = entry
            else:
                plist.append(entry)
        info(f"updated workspace {ws_name!r} (+{len(entries)} project path(s))")

    dump_config(config_path, cfg)
    info(f"config: {config_path}")
    info("Next: orcan sync && orcan down && orcan up")
    return cfg


# ── curses UI ────────────────────────────────────────────────────────────────

def _run_curses(args: argparse.Namespace) -> int:
    try:
        import curses
    except ImportError as exc:
        die(f"curses not available: {exc}")

    parent = Path(args.dir).expanduser() if args.dir else None
    state = load_state()
    if parent is None:
        last = str(state.get("last_parent") or "").strip()
        parent = Path(last).expanduser() if last else Path.cwd()
    depth = max(1, int(args.depth))

    workspace = (args.workspace or str(state.get("last_workspace") or "")).strip()
    if not workspace:
        workspace = default_workspace_name(parent)
    use_worktree = bool(args.branch) or bool(state.get("last_use_worktree"))
    branch = (args.branch or str(state.get("last_branch") or "feature/work")).strip()
    cursor = 0
    selected: set[Path] = set()
    message = ""
    scroll = 0

    def refresh_repos() -> list[Path]:
        nonlocal message
        try:
            repos_local = scan_repos(parent, max_depth=depth)
            message = f"{len(repos_local)} repo(s) under {parent}"
            return repos_local
        except SystemExit as exc:
            message = str(exc.args[0]) if exc.args else "scan failed"
            return []

    repos = refresh_repos()
    if args.select:
        wanted = {s.strip() for s in args.select.split(",") if s.strip()}
        for r in repos:
            if r.name in wanted or str(r) in wanted:
                selected.add(r)

    def draw(stdscr: Any) -> None:
        nonlocal scroll
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        title = " orcan context tui "
        stdscr.addnstr(0, 0, title.ljust(w), w, curses.A_REVERSE)
        stdscr.addnstr(1, 0, f" Parent: {parent}"[: w - 1], w - 1)
        mode = f"worktrees @{branch}" if use_worktree else "mount paths as-is"
        stdscr.addnstr(
            2,
            0,
            f" Workspace: {workspace}  |  Mode: {mode}"[: w - 1],
            w - 1,
        )
        stdscr.addnstr(
            3,
            0,
            " Space toggle · a/A all/none · e path · w name · t worktree · b branch · Enter apply · q quit"
            [: w - 1],
            w - 1,
            curses.A_DIM,
        )

        list_top = 5
        list_h = max(1, h - list_top - 2)
        if cursor < scroll:
            scroll = cursor
        if cursor >= scroll + list_h:
            scroll = cursor - list_h + 1

        if not repos:
            stdscr.addnstr(list_top, 0, "  (no git repos found — press e to change path)"[: w - 1], w - 1)
        else:
            for i in range(list_h):
                idx = scroll + i
                if idx >= len(repos):
                    break
                repo = repos[idx]
                mark = "[x]" if repo in selected else "[ ]"
                line = f" {mark} {repo.name}  {repo}"
                attr = curses.A_REVERSE if idx == cursor else curses.A_NORMAL
                if repo in selected and idx != cursor:
                    attr |= curses.A_BOLD
                stdscr.addnstr(list_top + i, 0, line[: w - 1], w - 1, attr)

        footer = message or f"{len(selected)} selected"
        stdscr.addnstr(h - 1, 0, footer.ljust(w)[:w], w, curses.A_REVERSE)
        stdscr.refresh()

    def prompt_line(stdscr: Any, label: str, initial: str) -> str | None:
        curses.echo()
        curses.curs_set(1)
        h, w = stdscr.getmaxyx()
        stdscr.addnstr(h - 1, 0, " " * (w - 1), w - 1)
        stdscr.addnstr(h - 1, 0, f"{label}: {initial}"[: w - 1], w - 1)
        stdscr.move(h - 1, min(len(label) + 2, w - 2))
        try:
            raw = stdscr.getstr(h - 1, min(len(label) + 2, w - 2), max(8, w - len(label) - 4))
        except KeyboardInterrupt:
            raw = b""
        curses.noecho()
        curses.curs_set(0)
        if raw is None:
            return None
        text = raw.decode("utf-8", errors="replace").strip()
        return text if text else initial

    def main_loop(stdscr: Any) -> int:
        nonlocal parent, workspace, use_worktree, branch, cursor, selected, message, repos
        curses.curs_set(0)
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()

        while True:
            draw(stdscr)
            key = stdscr.getch()
            if key in (ord("q"), 27):
                return 1
            if key in (curses.KEY_UP, ord("k")):
                cursor = max(0, cursor - 1)
            elif key in (curses.KEY_DOWN, ord("j")):
                cursor = min(max(0, len(repos) - 1), cursor + 1)
            elif key == ord(" "):
                if repos:
                    r = repos[cursor]
                    if r in selected:
                        selected.discard(r)
                    else:
                        selected.add(r)
            elif key == ord("a"):
                selected = set(repos)
            elif key == ord("A"):
                selected = set()
            elif key == ord("e"):
                new_path = prompt_line(stdscr, "Parent directory", str(parent))
                if new_path:
                    candidate = Path(new_path).expanduser()
                    if candidate.is_dir():
                        parent = candidate.resolve()
                        repos = refresh_repos()
                        selected &= set(repos)
                        cursor = 0
                        if not workspace or workspace == default_workspace_name(Path(".")):
                            workspace = default_workspace_name(parent)
                    else:
                        message = f"not a directory: {candidate}"
            elif key == ord("w"):
                workspace = prompt_line(stdscr, "Workspace name", workspace) or workspace
            elif key == ord("t"):
                use_worktree = not use_worktree
                message = "worktrees ON" if use_worktree else "mount as-is"
            elif key == ord("b"):
                branch = prompt_line(stdscr, "Branch for all worktrees", branch) or branch
                use_worktree = True
            elif key in (curses.KEY_ENTER, 10, 13):
                if not selected:
                    message = "select at least one repo (Space)"
                    continue
                if not NAME_RE.match(workspace):
                    message = "invalid workspace name"
                    continue
                if use_worktree and not branch.strip():
                    message = "branch required when worktrees are on (press b)"
                    continue
                # Leave curses before applying (git output).
                return 0
        return 1

    rc = curses.wrapper(main_loop)
    if rc != 0:
        info("cancelled")
        return rc

    chosen = sorted(selected, key=lambda p: p.name.lower())
    save_state(
        {
            "last_parent": str(parent.resolve()),
            "last_workspace": workspace,
            "last_branch": branch,
            "last_use_worktree": use_worktree,
        }
    )
    config_path = resolve_config(args.config)
    apply_selection(
        config_path=config_path,
        workspace=workspace,
        repos=chosen,
        branch=branch if use_worktree else None,
        force=bool(args.force),
        start_point=args.start_point,
    )
    if args.sync:
        return _run_sync()
    info("Run: orcan sync && orcan down && orcan up")
    return 0


def _run_sync() -> int:
    # Prefer invoking sibling CLI if ORCAN_ROOT is set; else remind the user.
    root = os.environ.get("ORCAN_ROOT")
    if not root:
        info("ORCAN_ROOT unset — run: orcan sync")
        return 0
    import subprocess

    orcan_bin = Path(root) / "bin" / "orcan"
    if not orcan_bin.is_file():
        info("run: orcan sync")
        return 0
    info("Running orcan sync…")
    proc = subprocess.run([str(orcan_bin), "sync"], check=False)
    return int(proc.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="TUI: select repos under a folder → workspace (+ optional shared branch worktrees)"
    )
    parser.add_argument(
        "--dir",
        default="",
        help="Parent directory to scan (default: last used or cwd)",
    )
    parser.add_argument("--workspace", default="", help="Workspace name")
    parser.add_argument(
        "--branch",
        default="",
        help="If set, create managed worktrees on this branch for every selected repo",
    )
    parser.add_argument(
        "--select",
        default="",
        help="Comma-separated repo names or paths to pre-select / use non-interactively",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Non-interactive: require --dir and --select; skip curses",
    )
    parser.add_argument("--force", action="store_true", help="Replace existing workspace/projects")
    parser.add_argument("--config", default="", help="orcan.config.json path")
    parser.add_argument("--start-point", default="HEAD", help="git worktree start point")
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Run orcan sync after writing config",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=2,
        help="Scan depth under parent (1=children only, 2=also grandchildren)",
    )
    args = parser.parse_args()

    if args.yes:
        if not args.dir:
            die("--yes requires --dir")
        if not args.select:
            die("--yes requires --select name1,name2")
        parent = Path(args.dir).expanduser().resolve()
        repos = scan_repos(parent, max_depth=max(1, args.depth))
        wanted = {s.strip() for s in args.select.split(",") if s.strip()}
        chosen = [r for r in repos if r.name in wanted or str(r) in wanted]
        if not chosen:
            die(f"no matching repos for --select among: {[r.name for r in repos]}")
        workspace = (args.workspace or default_workspace_name(parent)).strip()
        config_path = resolve_config(args.config)
        apply_selection(
            config_path=config_path,
            workspace=workspace,
            repos=chosen,
            branch=(args.branch or None),
            force=bool(args.force),
            start_point=args.start_point,
        )
        save_state(
            {
                "last_parent": str(parent),
                "last_workspace": workspace,
                "last_branch": args.branch or "",
                "last_use_worktree": bool(args.branch),
            }
        )
        raise SystemExit(_run_sync() if args.sync else 0)

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        die("not a TTY — use: orcan context tui --yes --dir DIR --select a,b [--branch NAME]")

    raise SystemExit(_run_curses(args))


if __name__ == "__main__":
    main()
