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
import subprocess
import sys
import time
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
from git_worktrees import (  # noqa: E402
    is_git_repo,
    is_under_managed_root,
    load_manifest,
    manifest_remove,
    remove_worktree,
    safe_segment,
)
from managed_workspace import create_managed_workspace, find_workspace  # noqa: E402

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,48}$")
STATE_NAME = "context-tui-state.json"
HISTORY_LIMIT = 8
HISTORY_TTL_DAYS = 3.0

# curses color pair numbers, shared across screens once initialized by
# _init_curses_session() — semantic, not decorative: warn=caution, info=fyi
# tag, danger=irreversible data loss.
_COLOR_WARN = 1
_COLOR_INFO = 2
_COLOR_DANGER = 3


def _init_curses_session() -> None:
    """Per-session curses setup shared by every screen: colors, and a short
    ESCDELAY. ncurses waits ~1000ms after a bare Esc before delivering it (to
    tell it apart from an arrow-key escape sequence) — over SSH/a mobile
    terminal that reads as "Esc doesn't work". 25ms is the common fix."""
    import curses

    if hasattr(curses, "set_escdelay"):
        try:
            curses.set_escdelay(25)
        except curses.error:
            pass
    if not curses.has_colors():
        return
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(_COLOR_WARN, curses.COLOR_YELLOW, -1)
    curses.init_pair(_COLOR_INFO, curses.COLOR_CYAN, -1)
    curses.init_pair(_COLOR_DANGER, curses.COLOR_RED, -1)


def die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def info(msg: str = "") -> None:
    print(msg)


def state_path() -> Path:
    return ROOT / "mounts" / STATE_NAME


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


def scan_dirs(parent: Path, *, max_depth: int = 2) -> list[tuple[Path, bool]]:
    """Find git repos AND plain directories under parent (depth 1 = children,
    2 = grandchildren of non-repo children). Each entry is (path, is_git) —
    plain dirs are still selectable (mount as-is only; no managed worktree,
    since that needs a git repo to branch from)."""
    parent = parent.expanduser().resolve()
    if not parent.is_dir():
        die(f"not a directory: {parent}")

    found: list[tuple[Path, bool]] = []
    seen: set[Path] = set()

    def consider(path: Path) -> None:
        try:
            resolved = path.resolve()
        except OSError:
            return
        if resolved in seen or not resolved.is_dir():
            return
        seen.add(resolved)
        found.append((resolved, is_git_repo(resolved)))

    # Parent itself may be a monorepo root
    if is_git_repo(parent):
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

    # Prefer nested repos over listing the parent when parent is not the only git hit
    git_hits = [p for p, is_git in found if is_git]
    if len(git_hits) > 1 and parent in git_hits:
        # Keep parent only if it is the sole repo; else drop it so multi-project
        # folders (many child repos) stay the focus.
        found = [entry for entry in found if entry[0] != parent]

    return found


def scan_repos(parent: Path, *, max_depth: int = 2) -> list[Path]:
    """Git repos only under parent — thin filter over scan_dirs(), kept for
    the --yes/--select non-interactive path."""
    return [p for p, is_git in scan_dirs(parent, max_depth=max_depth) if is_git]


def list_subdirs(path: Path) -> list[Path]:
    """Direct, non-hidden subdirectories of path, sorted by name. Empty on error."""
    try:
        return sorted(
            (p for p in path.iterdir() if p.is_dir() and not p.name.startswith(".")),
            key=lambda p: p.name.lower(),
        )
    except OSError:
        return []


def worktree_is_dirty(path: Path) -> bool:
    """True if the git worktree at path has uncommitted changes (including
    untracked files). False if that can't be determined (missing dir, not a
    repo, git failed/timed out) — a failed check must not block a legitimate
    removal, it only skips the extra warning. Pure/curses-free."""
    if not path.is_dir():
        return False
    try:
        r = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and bool(r.stdout.strip())


def _ellipsize(text: str, width: int) -> str:
    """Truncate text to width, marking truncation with an ellipsis instead of
    silently cutting it off — so a long path reads as 'cut here', not as the
    whole path. Pure/curses-free."""
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width == 1:
        return "…"
    return text[: width - 1] + "…"


def resolve_config(path: str) -> Path:
    if path:
        p = Path(path)
        if not p.is_absolute():
            p = (ROOT / p).resolve()
        return p
    return discover_config(ROOT) or default_write_path(ROOT)


def _humanize(seconds: float) -> str:
    """Coarse duration like '5m', '3h', '2d' — used for history age/TTL display."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h"
    return f"{hours // 24}d"


def update_parent_history(
    existing: list[Any],
    parent: Path,
    *,
    limit: int = HISTORY_LIMIT,
    ttl_days: float = HISTORY_TTL_DAYS,
    now: float | None = None,
) -> list[dict[str, Any]]:
    """Move parent to the front of history with a fresh timestamp, dropping
    duplicates, dirs that no longer exist, and entries past the TTL — so an
    unused dir quietly falls out instead of accumulating forever.
    Pure/curses-free so it's directly unit-testable."""
    now = time.time() if now is None else now
    cutoff = now - ttl_days * 86400
    p = str(parent)
    kept: list[dict[str, Any]] = []
    for h in existing:
        if not isinstance(h, dict):
            continue
        path, ts = h.get("path"), h.get("ts")
        if not isinstance(path, str) or not isinstance(ts, (int, float)):
            continue
        if path == p or ts < cutoff or not Path(path).is_dir():
            continue
        kept.append({"path": path, "ts": ts})
    return [{"path": p, "ts": now}] + kept[: max(0, limit - 1)]


def default_workspace_name(parent: Path) -> str:
    name = parent.name.strip() or "workspace"
    if NAME_RE.match(name):
        return name
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-_")
    return cleaned[:48] or "workspace"


def existing_project_names(config_path: Path, workspace: str) -> set[str]:
    """Project names already present in `workspace` within config_path (empty
    if the config or workspace doesn't exist yet). Compares raw directory
    names rather than safe_segment()'s sanitized form, so it can't itself
    die() mid-prompt on an odd name — good enough for a pre-apply warning.
    Pure/curses-free."""
    if not config_path.is_file():
        return set()
    cfg = load_config(config_path)
    ws = find_workspace(cfg, workspace)
    if not ws:
        return set()
    return {
        str(p.get("name"))
        for p in ws.get("projects") or []
        if isinstance(p, dict) and p.get("name")
    }


def find_path_conflicts(config_path: Path, paths: list[Path]) -> dict[str, str]:
    """Map str(path) -> workspace name, for any of `paths` already configured
    (under any name) in config_path — so mounting the same checkout into a
    second workspace by accident gets flagged instead of happening silently.
    Pure/curses-free."""
    if not config_path.is_file():
        return {}
    cfg = load_config(config_path)
    wanted = {str(p.resolve()) for p in paths}
    out: dict[str, str] = {}
    for ws in cfg.get("workspaces") or []:
        if not isinstance(ws, dict):
            continue
        for p in ws.get("projects") or []:
            if not isinstance(p, dict):
                continue
            path = str(p.get("path") or "")
            if path in wanted:
                out[path] = str(ws.get("name") or "")
    return out


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

def _prompt_line(stdscr: Any, label: str, initial: str, *, attr: int = 0) -> str | None:
    """Editable text prompt, pre-filled with `initial` and cursor at the end —
    Left/Right/Home/End/Backspace/Delete work like a normal line editor, so
    changing one character of a long path doesn't mean retyping it all.
    Ctrl-B/F/A/E are readline-style fallbacks for terminals without real
    arrow/Home/End keys (mobile terminal apps). Enter submits (empty submit
    keeps `initial`); Esc/Ctrl-C cancels (None). `attr` (e.g. a color pair)
    renders the label/text, for danger prompts."""
    import curses

    curses.curs_set(1)
    buf = list(initial)
    pos = len(buf)

    try:
        while True:
            h, w = stdscr.getmaxyx()
            row = h - 1
            field_col = min(len(label) + 2, w - 2)
            stdscr.addnstr(row, 0, " " * (w - 1), w - 1)
            stdscr.addnstr(row, 0, f"{label}: {''.join(buf)}"[: w - 1], w - 1, attr)
            stdscr.move(row, min(field_col + pos, w - 1))
            stdscr.refresh()
            try:
                key = stdscr.get_wch()
            except curses.error:
                continue

            if key == curses.KEY_RESIZE:
                continue
            if key in ("\n", "\r", curses.KEY_ENTER, 10, 13):
                text = "".join(buf).strip()
                return text if text else initial
            if key in (chr(27), 27):
                return None
            if key in ("\x7f", "\b", curses.KEY_BACKSPACE, 8):
                if pos > 0:
                    del buf[pos - 1]
                    pos -= 1
            elif key == curses.KEY_DC:
                if pos < len(buf):
                    del buf[pos]
            elif key in (curses.KEY_LEFT, chr(2), 2):  # Ctrl-B: back one char
                pos = max(0, pos - 1)
            elif key in (curses.KEY_RIGHT, chr(6), 6):  # Ctrl-F: forward one char
                pos = min(len(buf), pos + 1)
            elif key in (curses.KEY_HOME, chr(1), 1):  # Ctrl-A: start of line
                pos = 0
            elif key in (curses.KEY_END, chr(5), 5):  # Ctrl-E: end of line
                pos = len(buf)
            elif isinstance(key, str) and key.isprintable():
                buf.insert(pos, key)
                pos += 1
    except KeyboardInterrupt:
        return None
    finally:
        curses.curs_set(0)


def _confirm_line(stdscr: Any, label: str, *, default: bool = False, danger: bool = False) -> bool:
    import curses

    attr = curses.color_pair(_COLOR_DANGER) | curses.A_BOLD if danger and curses.has_colors() else 0
    raw = _prompt_line(stdscr, f"{label} ({'Y/n' if default else 'y/N'})", "", attr=attr)
    if not raw:
        return default
    return raw.strip().lower() in ("y", "yes")


def _browse_dir(stdscr: Any, start: Path) -> Path | None:
    """Arrow-navigate directories: Enter opens '..'/a subfolder, s selects the
    current one, f filters entries by name, / falls back to typing a path
    outright. Returns None on cancel."""
    import curses

    current = start.expanduser()
    if not current.is_dir():
        current = Path.home()
    current = current.resolve()
    cursor = 0
    scroll = 0
    message = ""
    filter_text = ""

    while True:
        entries = list_subdirs(current)
        if filter_text:
            ft = filter_text.lower()
            entries = [p for p in entries if ft in p.name.lower()]
        names = [".. (up)"] + [p.name for p in entries]
        cursor = max(0, min(cursor, len(names) - 1))

        stdscr.erase()
        h, w = stdscr.getmaxyx()
        stdscr.addnstr(0, 0, " choose parent directory ".ljust(w), w, curses.A_REVERSE)
        stdscr.addnstr(1, 0, _ellipsize(f" {current}", w - 1), w - 1, curses.A_BOLD)
        stdscr.addnstr(
            2, 0,
            " Up/Down move · Enter open · s select this dir · f filter · / type path · q cancel"[: w - 1],
            w - 1, curses.A_DIM,
        )
        if filter_text:
            stdscr.addnstr(3, 0, f" filter: {filter_text}  (f to edit, empty to clear)"[: w - 1], w - 1, curses.A_DIM)

        list_top = 4
        list_h = max(1, h - list_top - 2)
        if cursor < scroll:
            scroll = cursor
        if cursor >= scroll + list_h:
            scroll = cursor - list_h + 1
        for i in range(list_h):
            idx = scroll + i
            if idx >= len(names):
                break
            attr = curses.A_REVERSE if idx == cursor else curses.A_NORMAL
            stdscr.addnstr(list_top + i, 0, f" {names[idx]}"[: w - 1], w - 1, attr)

        footer = message or "s to pick this folder"
        stdscr.addnstr(h - 1, 0, footer.ljust(w - 1)[: w - 1], w - 1, curses.A_REVERSE)
        stdscr.refresh()
        message = ""

        key = stdscr.getch()
        if key == curses.KEY_RESIZE:
            continue
        if key in (ord("q"), 27):
            return None
        if key in (curses.KEY_UP, ord("k")):
            cursor = max(0, cursor - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            cursor = min(len(names) - 1, cursor + 1)
        elif key == ord("s"):
            return current
        elif key == ord("f"):
            typed = _prompt_line(stdscr, "Filter (empty to clear)", filter_text)
            filter_text = (typed or "").strip()
            cursor = 0
        elif key == ord("/"):
            typed = _prompt_line(stdscr, "Parent directory", str(current))
            if typed:
                candidate = Path(typed).expanduser()
                if candidate.is_dir():
                    current = candidate.resolve()
                    cursor = 0
                    filter_text = ""
                else:
                    message = f"not a directory: {candidate}"
        elif key in (curses.KEY_ENTER, 10, 13):
            if cursor == 0:
                current = current.parent
            else:
                current = entries[cursor - 1]
            cursor = 0
            filter_text = ""


def _show_help(stdscr: Any, title: str, lines: list[str]) -> None:
    """Full-screen keybinding cheatsheet; any key dismisses it."""
    import curses

    stdscr.erase()
    h, w = stdscr.getmaxyx()
    stdscr.addnstr(0, 0, f" {title} ".ljust(w), w, curses.A_REVERSE)
    for i, line in enumerate(lines):
        row = i + 2
        if row >= h - 1:
            break
        stdscr.addnstr(row, 0, _ellipsize(f"  {line}", w - 1), w - 1)
    stdscr.addnstr(h - 1, 0, " press any key to close ".ljust(w - 1)[: w - 1], w - 1, curses.A_REVERSE)
    stdscr.refresh()
    stdscr.getch()


def _pick_from_history(stdscr: Any, items: list[tuple[str, str]]) -> str | None:
    """Small list picker for jumping straight to a recently used parent dir.
    items are (path, age/ttl label) pairs, newest first."""
    import curses

    cursor = 0
    scroll = 0
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        stdscr.addnstr(0, 0, " recent parent directories ".ljust(w), w, curses.A_REVERSE)
        stdscr.addnstr(
            1, 0, " Up/Down move · Enter select · q cancel"[: w - 1], w - 1, curses.A_DIM
        )
        list_top = 3
        list_h = max(1, h - list_top - 1)
        if cursor < scroll:
            scroll = cursor
        if cursor >= scroll + list_h:
            scroll = cursor - list_h + 1
        for i in range(list_h):
            idx = scroll + i
            if idx >= len(items):
                break
            path, label = items[idx]
            line = f" {path}  ({label})"
            attr = curses.A_REVERSE if idx == cursor else curses.A_NORMAL
            stdscr.addnstr(list_top + i, 0, _ellipsize(line, w - 1), w - 1, attr)
        stdscr.refresh()

        key = stdscr.getch()
        if key == curses.KEY_RESIZE:
            continue
        if key in (ord("q"), 27):
            return None
        if key in (curses.KEY_UP, ord("k")):
            cursor = max(0, cursor - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            cursor = min(len(items) - 1, cursor + 1)
        elif key in (curses.KEY_ENTER, 10, 13):
            return items[cursor][0]


def _validate_manage_path(path_str: str) -> tuple[str | None, Path | None]:
    path_str = path_str.strip()
    if not path_str:
        return "path cannot be empty", None
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        return f"path must be absolute (got: {path_str})", None
    if not p.is_dir():
        return f"not a directory: {path_str}", None
    try:
        resolved = p.resolve()
    except OSError as exc:
        return f"cannot resolve path: {exc}", None
    return None, resolved


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
    filter_text = ""
    config_path = resolve_config(args.config)

    def refresh_repos() -> list[tuple[Path, bool]]:
        nonlocal message
        try:
            entries = scan_dirs(parent, max_depth=depth)
            n_git = sum(1 for _, is_git in entries if is_git)
            n_plain = len(entries) - n_git
            message = f"{n_git} repo(s), {n_plain} plain dir(s) under {parent}"
            return entries
        except SystemExit as exc:
            message = str(exc.args[0]) if exc.args else "scan failed"
            return []

    def visible_repos() -> list[tuple[Path, bool]]:
        if not filter_text:
            return repos
        ft = filter_text.lower()
        return [entry for entry in repos if ft in entry[0].name.lower()]

    repos = refresh_repos()
    if args.select:
        wanted = {s.strip() for s in args.select.split(",") if s.strip()}
        for r, _is_git in repos:
            if r.name in wanted or str(r) in wanted:
                selected.add(r)

    def draw(stdscr: Any) -> None:
        nonlocal scroll
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        title = " orcan context tui "
        stdscr.addnstr(0, 0, title.ljust(w), w, curses.A_REVERSE)
        stdscr.addnstr(1, 0, _ellipsize(f" Parent: {parent}", w - 1), w - 1)
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
            " Space toggle · a/A all/none · / filter · e browse dir · h history · w name · t worktree · b branch · Enter apply · ? help · q quit"
            [: w - 1],
            w - 1,
            curses.A_DIM,
        )
        if filter_text:
            stdscr.addnstr(4, 0, f" filter: {filter_text}  (/ to edit, empty to clear)"[: w - 1], w - 1, curses.A_DIM)

        view = visible_repos()
        list_top = 5
        list_h = max(1, h - list_top - 2)
        if cursor < scroll:
            scroll = cursor
        if cursor >= scroll + list_h:
            scroll = cursor - list_h + 1

        if not view:
            hint = "no matches — / to change filter" if filter_text else "nothing found — press e to browse to another folder"
            stdscr.addnstr(list_top, 0, f"  ({hint})"[: w - 1], w - 1)
        else:
            for i in range(list_h):
                idx = scroll + i
                if idx >= len(view):
                    break
                repo, is_git = view[idx]
                mark = "[x]" if repo in selected else "[ ]"
                tag = "" if is_git else "  (no git — mount only)"
                line = f" {mark} {repo.name}{tag}  {repo}"
                attr = curses.A_REVERSE if idx == cursor else curses.A_NORMAL
                if repo in selected and idx != cursor:
                    attr |= curses.A_BOLD
                if not is_git and idx != cursor:
                    attr |= curses.color_pair(_COLOR_WARN)
                stdscr.addnstr(list_top + i, 0, _ellipsize(line, w - 1), w - 1, attr)

        footer = message or f"{len(selected)} selected"
        stdscr.addnstr(h - 1, 0, footer.ljust(w - 1)[: w - 1], w - 1, curses.A_REVERSE)
        stdscr.refresh()

    def main_loop(stdscr: Any) -> int:
        nonlocal parent, workspace, use_worktree, branch, cursor, selected, message, repos, filter_text
        curses.curs_set(0)
        _init_curses_session()

        while True:
            draw(stdscr)
            view = visible_repos()
            key = stdscr.getch()
            if key == curses.KEY_RESIZE:
                continue
            if key in (ord("q"), 27):
                return 1
            if key in (curses.KEY_UP, ord("k")):
                cursor = max(0, cursor - 1)
            elif key in (curses.KEY_DOWN, ord("j")):
                cursor = min(max(0, len(view) - 1), cursor + 1)
            elif key == ord(" "):
                if view:
                    r, _is_git = view[min(cursor, len(view) - 1)]
                    if r in selected:
                        selected.discard(r)
                    else:
                        selected.add(r)
            elif key == ord("a"):
                selected |= {p for p, _ in view}
            elif key == ord("A"):
                selected = set()
            elif key == ord("/"):
                typed = _prompt_line(stdscr, "Filter (empty to clear)", filter_text)
                filter_text = (typed or "").strip()
                cursor = 0
            elif key == ord("?"):
                _show_help(
                    stdscr,
                    "orcan context tui — scan screen",
                    [
                        "Space    toggle selection",
                        "a / A    select all visible / clear selection",
                        "/        filter the list by name",
                        "e        browse to a different parent directory",
                        "h        jump to a recently used parent directory",
                        "w        set workspace name",
                        "t        toggle worktree mode on/off",
                        "b        set branch (implies worktree mode)",
                        "Enter    apply — create/append the workspace",
                        "q / Esc  quit without applying",
                        "?        this help",
                    ],
                )
            elif key == ord("e"):
                chosen_dir = _browse_dir(stdscr, parent)
                if chosen_dir is not None:
                    parent = chosen_dir
                    repos = refresh_repos()
                    selected &= {p for p, _ in repos}
                    cursor = 0
                    filter_text = ""
                    if not workspace or workspace == default_workspace_name(Path(".")):
                        workspace = default_workspace_name(parent)
            elif key == ord("h"):
                now = time.time()
                hist: list[tuple[str, str]] = []
                for h in state.get("parent_history") or []:
                    if not isinstance(h, dict):
                        continue
                    path, ts = h.get("path"), h.get("ts")
                    if not isinstance(path, str) or not isinstance(ts, (int, float)):
                        continue
                    age = now - ts
                    if path == str(parent) or age > HISTORY_TTL_DAYS * 86400 or not Path(path).is_dir():
                        continue
                    remaining = HISTORY_TTL_DAYS * 86400 - age
                    hist.append((path, f"{_humanize(age)} ago · expires in {_humanize(remaining)}"))
                if not hist:
                    message = "no history yet"
                else:
                    picked = _pick_from_history(stdscr, hist)
                    if picked:
                        parent = Path(picked).resolve()
                        repos = refresh_repos()
                        selected &= {p for p, _ in repos}
                        cursor = 0
                        filter_text = ""
                        if not workspace or workspace == default_workspace_name(Path(".")):
                            workspace = default_workspace_name(parent)
            elif key == ord("w"):
                workspace = _prompt_line(stdscr, "Workspace name", workspace) or workspace
            elif key == ord("t"):
                use_worktree = not use_worktree
                message = "worktrees ON" if use_worktree else "mount as-is"
            elif key == ord("b"):
                branch = _prompt_line(stdscr, "Branch for all worktrees", branch) or branch
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
                conflicts = existing_project_names(config_path, workspace) & {p.name for p in selected}
                if conflicts and not _confirm_line(
                    stdscr,
                    f"{len(conflicts)} project(s) already in {workspace!r} "
                    f"({', '.join(sorted(conflicts))}) — replace?",
                ):
                    message = "apply cancelled (name conflict)"
                    continue
                if conflicts:
                    args.force = True
                cross = {
                    path: ws_name
                    for path, ws_name in find_path_conflicts(config_path, list(selected)).items()
                    if ws_name != workspace
                }
                if cross and not _confirm_line(
                    stdscr,
                    f"{len(cross)} path(s) already used in other workspace(s) "
                    f"({', '.join(sorted(set(cross.values())))}) — mount anyway?",
                ):
                    message = "apply cancelled (already used elsewhere)"
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
            "parent_history": update_parent_history(state.get("parent_history") or [], parent),
        }
    )
    if use_worktree:
        git_chosen = [p for p in chosen if is_git_repo(p)]
        plain_chosen = [p for p in chosen if not is_git_repo(p)]
        if git_chosen:
            apply_selection(
                config_path=config_path,
                workspace=workspace,
                repos=git_chosen,
                branch=branch,
                force=bool(args.force),
                start_point=args.start_point,
            )
        if plain_chosen:
            apply_selection(
                config_path=config_path,
                workspace=workspace,
                repos=plain_chosen,
                branch=None,
                force=bool(args.force),
                start_point=args.start_point,
            )
            names = ", ".join(p.name for p in plain_chosen)
            info(
                f"note: {len(plain_chosen)} selected path(s) are not git repos "
                f"({names}) — mounted as-is, no worktree/branch isolation. "
                "Edits there go straight to the shared directory; be careful."
            )
    else:
        apply_selection(
            config_path=config_path,
            workspace=workspace,
            repos=chosen,
            branch=None,
            force=bool(args.force),
            start_point=args.start_point,
        )
    if args.sync:
        return _run_sync()
    info("Run: orcan sync && orcan down && orcan up")
    return 0


def manage_rows(workspaces: list[Any]) -> list[tuple[str, int, int | None]]:
    """(kind, ws_idx, proj_idx) — kind 'ws' or 'proj'; proj_idx None for 'ws'.
    Pure/curses-free so it's directly unit-testable."""
    out: list[tuple[str, int, int | None]] = []
    for wi, ws in enumerate(workspaces):
        if not isinstance(ws, dict):
            continue
        out.append(("ws", wi, None))
        projects = ws.get("projects")
        if isinstance(projects, list):
            for pi, p in enumerate(projects):
                if isinstance(p, dict):
                    out.append(("proj", wi, pi))
    return out


def manage_rename_workspace(workspaces: list[Any], wi: int, new_name: str) -> str | None:
    """Returns an error message, or None on success (mutates in place)."""
    if not NAME_RE.match(new_name):
        return "invalid workspace name"
    for idx, ws in enumerate(workspaces):
        if idx != wi and isinstance(ws, dict) and ws.get("name") == new_name:
            return f"workspace {new_name!r} already exists"
    workspaces[wi]["name"] = new_name
    return None


def manage_rename_project(ws: dict[str, Any], pi: int, new_name: str) -> str | None:
    if not NAME_RE.match(new_name):
        return "invalid project name"
    projects = ws.get("projects") or []
    for idx, p in enumerate(projects):
        if idx != pi and isinstance(p, dict) and p.get("name") == new_name:
            return f"project {new_name!r} already in this workspace"
    projects[pi]["name"] = new_name
    return None


def manage_change_project_path(ws: dict[str, Any], pi: int, new_path: str) -> str | None:
    err, resolved = _validate_manage_path(new_path)
    if err:
        return err
    (ws.get("projects") or [])[pi]["path"] = str(resolved)
    return None


def manage_delete_project(ws: dict[str, Any], pi: int) -> dict[str, Any]:
    return ws["projects"].pop(pi)


def manage_delete_workspace(workspaces: list[Any], wi: int) -> dict[str, Any]:
    return workspaces.pop(wi)


def managed_projects(ws: dict[str, Any]) -> list[dict[str, Any]]:
    """Projects in ws whose path lives under the managed worktree root
    (i.e. was created via --branch / managed_workspace.create). Pure/curses-free."""
    out = []
    for p in ws.get("projects") or []:
        if isinstance(p, dict) and p.get("path") and is_under_managed_root(Path(str(p["path"]))):
            out.append(p)
    return out


def _run_prune_interactive(config_path: Path) -> None:
    """Plain-terminal prune pass — curses is torn down first since cmd_prune
    print()s directly and would otherwise fight the curses screen. Reuses
    cmd_prune's own dry-run-then-force flow rather than re-deriving it:
    calling it a second time with force=True is a no-op if there was
    nothing to prune, so no output-capturing is needed to decide whether
    to ask."""
    from git_worktrees import cmd_prune

    ns = argparse.Namespace(config=str(config_path), force=False)
    print()
    print("Checking managed worktrees for orphans / stale entries...")
    try:
        cmd_prune(ns)
    except SystemExit:
        pass
    resp = input("\nRemove the above with --force? (y/N): ").strip().lower()
    if resp in ("y", "yes"):
        ns.force = True
        try:
            cmd_prune(ns)
        except SystemExit:
            pass
    input("\nPress Enter to return to orcan init...")


def _run_manage(args: argparse.Namespace) -> int:
    """Curses screen for editing an existing orcan.config.json: rename /
    change path / delete projects and workspaces, without walking every
    project one at a time (unlike config-wizard.py's edit_existing())."""
    try:
        import curses
    except ImportError as exc:
        die(f"curses not available: {exc}")

    config_path = resolve_config(args.config)
    cfg = load_config(config_path) if config_path.is_file() else {"workspaces": []}
    workspaces = cfg.get("workspaces")
    if not isinstance(workspaces, list):
        workspaces = []
        cfg["workspaces"] = workspaces

    state = {"dirty": False, "cursor": 0, "scroll": 0, "message": ""}

    def rows() -> list[tuple[str, int, int | None]]:
        return manage_rows(workspaces)

    def draw(stdscr: Any) -> None:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        stdscr.addnstr(0, 0, " orcan init — manage workspaces ".ljust(w), w, curses.A_REVERSE)
        stdscr.addnstr(1, 0, _ellipsize(f" Config: {config_path}", w - 1), w - 1)
        stdscr.addnstr(
            2,
            0,
            (
                " j/k move · Enter/r rename · p path · a add project · d delete project · "
                "W delete workspace · n new (scan folder) · P prune orphans · s save · ? help · q quit"
            )[: w - 1],
            w - 1,
            curses.A_DIM,
        )

        current_rows = rows()
        list_top = 4
        list_h = max(1, h - list_top - 2)
        if state["cursor"] < state["scroll"]:
            state["scroll"] = state["cursor"]
        if state["cursor"] >= state["scroll"] + list_h:
            state["scroll"] = state["cursor"] - list_h + 1

        if not current_rows:
            stdscr.addnstr(
                list_top, 0, "  (no workspaces — press n to scan a folder)"[: w - 1], w - 1
            )
        else:
            for i in range(list_h):
                idx = state["scroll"] + i
                if idx >= len(current_rows):
                    break
                kind, wi, pi = current_rows[idx]
                ws = workspaces[wi]
                if kind == "ws":
                    n = len([p for p in (ws.get("projects") or []) if isinstance(p, dict)])
                    line = f" ▸ {ws.get('name')}  ({n} project{'s' if n != 1 else ''})"
                    attr = curses.A_BOLD
                else:
                    proj = (ws.get("projects") or [])[pi]
                    path_str = str(proj.get("path") or "")
                    is_managed = bool(path_str) and is_under_managed_root(Path(path_str))
                    tag = " [worktree]" if is_managed else ""
                    line = f"     {proj.get('name')}{tag}  →  {proj.get('path')}"
                    attr = curses.color_pair(_COLOR_INFO) if is_managed else curses.A_NORMAL
                if idx == state["cursor"]:
                    attr |= curses.A_REVERSE
                stdscr.addnstr(list_top + i, 0, _ellipsize(line, w - 1), w - 1, attr)

        footer = state["message"] or (
            f"{len(workspaces)} workspace(s)"
            + ("  — unsaved changes" if state["dirty"] else "")
        )
        stdscr.addnstr(h - 1, 0, footer.ljust(w - 1)[: w - 1], w - 1, curses.A_REVERSE)
        stdscr.refresh()

    def switch_to_scan(stdscr: Any) -> int:
        if state["dirty"]:
            dump_config(config_path, cfg)
            state["dirty"] = False
        return 2

    def main_loop(stdscr: Any) -> int:
        curses.curs_set(0)
        _init_curses_session()

        while True:
            current_rows = rows()
            if state["cursor"] >= len(current_rows):
                state["cursor"] = max(0, len(current_rows) - 1)
            draw(stdscr)
            key = stdscr.getch()
            if key == curses.KEY_RESIZE:
                continue
            state["message"] = ""

            if key in (ord("q"), 27):
                if state["dirty"]:
                    choice = (
                        _prompt_line(stdscr, "Save before quitting? (y/n/c to cancel)", "") or ""
                    )
                    c = choice.strip().lower()
                    if c in ("c", "cancel"):
                        continue
                    if c in ("y", "yes", ""):
                        dump_config(config_path, cfg)
                return 0
            if key in (curses.KEY_UP, ord("k")):
                state["cursor"] = max(0, state["cursor"] - 1)
                continue
            if key in (curses.KEY_DOWN, ord("j")):
                state["cursor"] = min(max(0, len(current_rows) - 1), state["cursor"] + 1)
                continue
            if key == ord("n"):
                return switch_to_scan(stdscr)
            if key == ord("s"):
                dump_config(config_path, cfg)
                state["dirty"] = False
                state["message"] = f"saved {config_path}"
                continue
            if key == ord("P"):
                if state["dirty"]:
                    dump_config(config_path, cfg)
                    state["dirty"] = False
                return 3
            if key == ord("?"):
                _show_help(
                    stdscr,
                    "orcan init — manage workspaces",
                    [
                        "j/k       move",
                        "Enter/r   rename workspace or project",
                        "p         change a project's path",
                        "a         add a project to this workspace (jumps to scan)",
                        "d         delete project (position on a project row)",
                        "W         delete whole workspace",
                        "n         new workspace (scan a folder)",
                        "P         prune orphaned/stale managed worktrees",
                        "s         save",
                        "q / Esc   quit",
                        "?         this help",
                    ],
                )
                continue
            if not current_rows:
                continue

            kind, wi, pi = current_rows[state["cursor"]]
            ws = workspaces[wi]

            if key in (ord("r"), curses.KEY_ENTER, 10, 13):
                if kind == "ws":
                    new_name = _prompt_line(stdscr, "Workspace name", str(ws.get("name") or ""))
                    if new_name:
                        err = manage_rename_workspace(workspaces, wi, new_name)
                        if err:
                            state["message"] = err
                        else:
                            state["dirty"] = True
                else:
                    proj = (ws.get("projects") or [])[pi]
                    new_name = _prompt_line(stdscr, "Project name", str(proj.get("name") or ""))
                    if new_name:
                        err = manage_rename_project(ws, pi, new_name)
                        if err:
                            state["message"] = err
                        else:
                            state["dirty"] = True
            elif key == ord("p"):
                if kind != "proj":
                    state["message"] = "position on a project to change its path"
                else:
                    proj = (ws.get("projects") or [])[pi]
                    new_path = _prompt_line(stdscr, "Project path", str(proj.get("path") or ""))
                    if new_path:
                        err = manage_change_project_path(ws, pi, new_path)
                        if err:
                            state["message"] = err
                        else:
                            state["dirty"] = True
            elif key == ord("d"):
                if kind != "proj":
                    state["message"] = "position on a project to delete it (W deletes a workspace)"
                else:
                    proj = (ws.get("projects") or [])[pi]
                    if _confirm_line(stdscr, f"Delete project {proj.get('name')!r}?"):
                        path = Path(str(proj.get("path") or ""))
                        is_managed = str(proj.get("path") or "") and is_under_managed_root(path)
                        remove_wt = is_managed and _confirm_line(
                            stdscr, "Also remove its managed worktree from disk (git worktree remove)?"
                        )
                        if remove_wt and worktree_is_dirty(path):
                            remove_wt = _confirm_line(
                                stdscr,
                                "This worktree has UNCOMMITTED CHANGES that will be "
                                "permanently lost — remove anyway?",
                                danger=True,
                            )
                        deleted = manage_delete_project(ws, pi)
                        state["dirty"] = True
                        if remove_wt:
                            try:
                                if path.exists():
                                    remove_worktree(path, force=True, allow_unmanaged=False)
                                manifest_remove(workspace=str(ws.get("name") or ""), project=str(deleted.get("name") or ""))
                                state["message"] = f"deleted {deleted.get('name')} + worktree"
                            except SystemExit as exc:
                                state["message"] = f"deleted from config; worktree removal failed: {exc}"
                        else:
                            state["message"] = f"deleted {deleted.get('name')}"
            elif key == ord("W"):
                if _confirm_line(stdscr, f"Delete whole workspace {ws.get('name')!r}?"):
                    managed = managed_projects(ws)
                    remove_wt = managed and _confirm_line(
                        stdscr, f"Also remove {len(managed)} managed worktree(s) from disk?"
                    )
                    if remove_wt:
                        dirty_names = [
                            str(p.get("name")) for p in managed if worktree_is_dirty(Path(str(p["path"])))
                        ]
                        if dirty_names and not _confirm_line(
                            stdscr,
                            f"{len(dirty_names)} of these have UNCOMMITTED CHANGES "
                            f"({', '.join(dirty_names)}) that will be permanently lost — remove anyway?",
                            danger=True,
                        ):
                            remove_wt = False
                    deleted = manage_delete_workspace(workspaces, wi)
                    state["dirty"] = True
                    if remove_wt:
                        failures = []
                        for p in managed:
                            path = Path(str(p["path"]))
                            try:
                                if path.exists():
                                    remove_worktree(path, force=True, allow_unmanaged=False)
                            except SystemExit as exc:
                                failures.append(f"{p.get('name')}: {exc}")
                        manifest_remove(workspace=str(deleted.get("name") or ""))
                        if failures:
                            state["message"] = f"deleted workspace {deleted.get('name')}; worktree removal failed: {'; '.join(failures)}"
                        else:
                            state["message"] = f"deleted workspace {deleted.get('name')} + {len(managed)} worktree(s)"
                    else:
                        state["message"] = f"deleted workspace {deleted.get('name')}"
            elif key == ord("a"):
                # Jump to the scan screen pre-loaded for THIS workspace: same
                # name (so picks append instead of creating a new workspace),
                # starting dir next to an existing project, and the same
                # managed-worktree branch if this workspace uses worktrees.
                ws_name = str(ws.get("name") or "")
                if state["dirty"]:
                    dump_config(config_path, cfg)
                    state["dirty"] = False
                args.workspace = ws_name
                projects = ws.get("projects") or []
                if not args.dir and projects:
                    first_path = Path(str(projects[0].get("path") or ""))
                    if first_path.exists():
                        args.dir = str(first_path.parent)
                if not args.branch:
                    entries = [e for e in load_manifest() if e.workspace == ws_name]
                    if entries:
                        args.branch = entries[0].branch
                return 2

    rc = curses.wrapper(main_loop)
    if rc == 2:
        return _run_curses(args)
    if rc == 3:
        _run_prune_interactive(config_path)
        return _run_manage(args)
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

    if not args.dir and not args.select:
        existing_path = resolve_config(args.config)
        if existing_path.is_file():
            existing_cfg = load_config(existing_path)
            if isinstance(existing_cfg.get("workspaces"), list) and existing_cfg["workspaces"]:
                raise SystemExit(_run_manage(args))

    raise SystemExit(_run_curses(args))


if __name__ == "__main__":
    main()
