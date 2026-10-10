#!/usr/bin/env python3
"""Terminal UI to build a workspace from a parent directory of repos.

Flow:
  1. Point at a parent folder (children-only scan by default; D / --depth 2
     for grandchildren). l/→ opens a folder; u/← goes up.
  2. Multi-select into a will-add stack (Tab reviews it; Space removes).
     Picks survive parent changes (e/h/u/l). h = recent picks. Enter opens
     a folder while the selection is empty, or applies selected projects.
  3. Name the workspace
  4. Optional: one branch → managed worktree per selected repo
  5. Write orcan.config.json (then caller may sync)

Stdlib only (curses). Non-interactive flags exist for scripts/tests.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("ORCAN_HOME") or Path(__file__).resolve().parents[2])
STATE_NAME = "context-tui-state.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_io import (
    default_write_path,
    die,
    discover_config,
    dump_config,
    load_config,
    load_config_or_create,
)
from context_mutations import (
    apply_selection,
    manage_rename_workspace,
    manage_rename_project,
    manage_change_project_path,
    manage_delete_project,
    manage_delete_workspace,
    managed_projects,
)
from context_presenters import (
    _ellipsize,
    _humanize,
    format_pick_label,
    manage_rows,
    review_outcome,
    selection_outside_scan,
    stack_apply_summary,
)
from context_selection import (
    NAME_RE,
    PICK_HISTORY_TTL_DAYS,
    classify_pick,
    default_workspace_name,
    existing_project_names,
    find_path_conflicts,
    list_subdirs,
    partition_selection_by_mode,
    scan_dirs,
    scan_repos,
    selection_mode_summary,
    update_parent_history,
    update_pick_history,
    workspace_membership,
    workspace_project_entries,
    worktree_is_dirty,
)
from git_worktrees import (
    is_git_repo,
    is_under_managed_root,
    load_manifest,
    manifest_remove,
    remove_worktree,
)

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


def resolve_config(path: str) -> Path:
    if path:
        p = Path(path)
        if not p.is_absolute():
            p = (ROOT / p).resolve()
        return p
    return discover_config(ROOT) or default_write_path(ROOT)


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


def _confirm_line(
    stdscr: Any, label: str, *, default: bool = False, danger: bool = False
) -> bool:
    import curses

    attr = (
        curses.color_pair(_COLOR_DANGER) | curses.A_BOLD
        if danger and curses.has_colors()
        else 0
    )
    raw = _prompt_line(
        stdscr, f"{label} ({'Y/n' if default else 'y/N'})", "", attr=attr
    )
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
            2,
            0,
            " Up/Down move · Enter open · s select this dir · f filter · / type path · q cancel"[
                : w - 1
            ],
            w - 1,
            curses.A_DIM,
        )
        if filter_text:
            stdscr.addnstr(
                3,
                0,
                f" filter: {filter_text}  (f to edit, empty to clear)"[: w - 1],
                w - 1,
                curses.A_DIM,
            )

        list_top = 4
        list_h = max(1, h - list_top - 2)
        scroll = min(scroll, cursor)
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
    stdscr.addnstr(
        h - 1,
        0,
        " press any key to close ".ljust(w - 1)[: w - 1],
        w - 1,
        curses.A_REVERSE,
    )
    stdscr.refresh()
    stdscr.getch()


def _recent_picks_screen(
    stdscr: Any,
    items: list[tuple[Path, str]],
    selected: list[Path],
) -> Path | None:
    """Add previously picked paths to the will-add stack without changing the
    current parent. Mutates `selected` in place. Returns a path to jump to
    (become the new scan parent) when the user presses o, else None."""
    import curses

    if not items:
        return None

    cursor = 0
    scroll = 0
    note = ""
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        stdscr.addnstr(
            0, 0, " recent picks — add without browsing ".ljust(w), w, curses.A_REVERSE
        )
        stdscr.addnstr(
            1,
            0,
            " Up/Down · Space toggle onto will-add · Enter/Esc done · o jump to its folder"[
                : w - 1
            ],
            w - 1,
            curses.A_DIM,
        )
        list_top = 3
        list_h = max(1, h - list_top - 1)
        scroll = min(scroll, cursor)
        if cursor >= scroll + list_h:
            scroll = cursor - list_h + 1
        for i in range(list_h):
            idx = scroll + i
            if idx >= len(items):
                break
            path, label = items[idx]
            mark = "[x]" if path in selected else "[ ]"
            line = f" {mark} {path.name}  {path}  ({label})"
            attr = curses.A_REVERSE if idx == cursor else curses.A_NORMAL
            if path in selected and idx != cursor:
                attr |= curses.A_BOLD
            stdscr.addnstr(list_top + i, 0, _ellipsize(line, w - 1), w - 1, attr)
        footer = (
            note
            or f"{sum(1 for p, _ in items if p in selected)} of {len(items)} in will-add"
        )
        stdscr.addnstr(h - 1, 0, footer.ljust(w - 1)[: w - 1], w - 1, curses.A_REVERSE)
        stdscr.refresh()
        note = ""

        key = stdscr.getch()
        if key == curses.KEY_RESIZE:
            continue
        if key in (ord("q"), 27, curses.KEY_ENTER, 10, 13):
            return None
        if key in (curses.KEY_UP, ord("k")):
            cursor = max(0, cursor - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            cursor = min(len(items) - 1, cursor + 1)
        elif key == ord(" "):
            path, _label = items[cursor]
            if path in selected:
                selected.remove(path)
                note = f"removed {path.name}"
            else:
                selected.append(path)
                note = f"added {path.name}"
        elif key == ord("o"):
            path, _label = items[cursor]
            # Scan the parent folder so this pick appears among siblings.
            target = path.parent if path.parent != path else path
            return target


def _review_selection_screen(
    stdscr: Any,
    selected: list[Path],
    *,
    workspace: str,
    repos: list[tuple[Path, bool]],
    names_in_ws: set[str],
    paths_in_ws: set[str],
    path_ws: dict[str, str],
    worktree_paths: set[Path],
    branch: str,
) -> bool:
    """Review the pending change. Enter accepts; Esc returns to browsing."""
    import curses

    cursor = 0
    scroll = 0
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        new_n, already_n = stack_apply_summary(selected, paths_in_ws=paths_in_ws)
        stdscr.addnstr(
            0, 0, " orcan init · review and apply ".ljust(w), w, curses.A_REVERSE
        )
        summary = f" Step 2/3 · workspace {workspace!r} · {new_n} to add"
        if already_n:
            summary += f" · {already_n} stay connected"
        stdscr.addnstr(1, 0, _ellipsize(summary, w - 1), w - 1, curses.A_BOLD)
        stdscr.addnstr(
            2,
            0,
            " ↑↓ inspect · b change mode · Space remove · Enter apply · Esc back"[
                : w - 1
            ],
            w - 1,
            curses.A_DIM,
        )
        list_top = 4
        list_h = max(1, h - list_top - 1)
        cursor = min(cursor, max(0, len(selected) - 1))
        scroll = min(scroll, cursor)
        if cursor >= scroll + list_h:
            scroll = cursor - list_h + 1
        for i in range(list_h):
            idx = scroll + i
            if idx >= len(selected):
                break
            path = selected[idx]
            bits = classify_pick(
                path,
                repos=repos,
                names_in_ws=names_in_ws,
                paths_in_ws=paths_in_ws,
                path_ws=path_ws,
                workspace=workspace,
            )
            mode = f"worktree @{branch}" if path in worktree_paths else "mount as-is"
            outcome = f"{mode} · {review_outcome(bits)}"
            line = f" {'›' if idx == cursor else ' '} {path.name} — {outcome}  {path}"
            attr = curses.A_REVERSE if idx == cursor else curses.A_NORMAL
            stdscr.addnstr(list_top + i, 0, _ellipsize(line, w - 1), w - 1, attr)
        footer = (
            f"Step 3/3 · Enter applies {new_n} new project(s)"
            if selected
            else "Nothing selected — Esc to return"
        )
        stdscr.addnstr(h - 1, 0, footer.ljust(w - 1)[: w - 1], w - 1, curses.A_REVERSE)
        stdscr.refresh()

        key = stdscr.getch()
        if key == curses.KEY_RESIZE:
            continue
        if key in (27, ord("q")):
            return False
        if key in (curses.KEY_UP, ord("k")):
            cursor = max(0, cursor - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            cursor = min(max(0, len(selected) - 1), cursor + 1)
        elif key in (ord(" "), ord("x")) and selected:
            worktree_paths.discard(selected[cursor])
            selected.pop(cursor)
            cursor = min(cursor, max(0, len(selected) - 1))
        elif key == ord("b") and selected:
            path = selected[cursor]
            if not is_git_repo(path):
                continue
            if path in worktree_paths:
                worktree_paths.remove(path)
            else:
                worktree_paths.add(path)
        elif key in (curses.KEY_ENTER, 10, 13) and selected:
            return True


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
    selected: list[Path] = []
    worktree_paths: set[Path] = set()
    message = ""
    scroll = 0
    filter_text = ""
    config_path = resolve_config(args.config)
    pick_history: list[Any] = list(state.get("pick_history") or [])

    def remember_picks(*paths: Path) -> None:
        nonlocal pick_history
        pick_history = update_pick_history(pick_history, list(paths))

    def refresh_repos() -> list[tuple[Path, bool]]:
        nonlocal message
        try:
            entries = scan_dirs(parent, max_depth=depth)
            n_git = sum(1 for _, is_git in entries if is_git)
            n_plain = len(entries) - n_git
            depth_note = "children only" if depth < 2 else "incl. grandchildren"
            message = (
                f"{n_git} repo(s), {n_plain} plain dir(s) under {parent}  "
                f"(depth {depth}: {depth_note}; D to toggle)"
            )
            return entries
        except SystemExit as exc:
            message = str(exc.args[0]) if exc.args else "scan failed"
            return []

    def visible_repos() -> list[tuple[Path, bool]]:
        if not filter_text:
            return repos
        ft = filter_text.lower()
        return [entry for entry in repos if ft in entry[0].name.lower()]

    def membership() -> tuple[set[str], set[str], dict[str, str]]:
        names, paths = workspace_membership(config_path, workspace)
        probe = list({*selected, *(p for p, _ in repos)})
        return names, paths, find_path_conflicts(config_path, probe)

    def after_parent_change() -> None:
        """Rescan after navigate/browse; keep selections across parents."""
        nonlocal repos, cursor, filter_text, message, workspace
        repos = refresh_repos()
        cursor = 0
        filter_text = ""
        outside = selection_outside_scan(selected, repos)
        if outside:
            message = f"{message} · kept {len(outside)} selection(s) from other folders"
        if not workspace or workspace == default_workspace_name(Path(".")):
            workspace = default_workspace_name(parent)

    def toggle_selected(path: Path) -> None:
        if path in selected:
            selected.remove(path)
            worktree_paths.discard(path)
        else:
            selected.append(path)
            if use_worktree and is_git_repo(path):
                worktree_paths.add(path)
            remember_picks(path)

    repos = refresh_repos()
    if args.select:
        wanted = {s.strip() for s in args.select.split(",") if s.strip()}
        for r, _is_git in repos:
            if (r.name in wanted or str(r) in wanted) and r not in selected:
                selected.append(r)
                if use_worktree and _is_git:
                    worktree_paths.add(r)

    def draw(stdscr: Any) -> None:
        nonlocal scroll
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        names_in_ws, paths_in_ws, path_ws = membership()
        existing_entries = workspace_project_entries(config_path, workspace)
        new_n, already_n = stack_apply_summary(selected, paths_in_ws=paths_in_ws)
        mount_n, worktree_n = selection_mode_summary(selected, worktree_paths)

        title = " orcan init · choose projects "
        stdscr.addnstr(0, 0, title.ljust(w), w, curses.A_REVERSE)
        stdscr.addnstr(1, 0, _ellipsize(f" Parent: {parent}", w - 1), w - 1)
        mode = f"default worktree @{branch}" if use_worktree else "default mount as-is"
        stdscr.addnstr(
            2,
            0,
            f" Step 1/3 · workspace {workspace}  |  {mode}  |  depth {depth}"[: w - 1],
            w - 1,
        )
        stdscr.addnstr(
            3,
            0,
            " ↑↓ choose · Space select · → open · Tab review · Enter apply · ? help"[
                : w - 1
            ],
            w - 1,
            curses.A_DIM,
        )
        if filter_text:
            stdscr.addnstr(
                4,
                0,
                f" filter: {filter_text}  (/ to edit, empty to clear)"[: w - 1],
                w - 1,
                curses.A_DIM,
            )

        view = visible_repos()
        list_top = 5 if filter_text else 4
        stack_w = 0
        split = w >= 88
        if split:
            stack_w = max(26, min(36, w // 3))
        bottom_stack_h = 0 if split else 1
        list_h = max(1, h - list_top - 1 - bottom_stack_h)
        left_w = (w - stack_w - 1) if split else w

        scroll = min(scroll, cursor)
        if cursor >= scroll + list_h:
            scroll = cursor - list_h + 1

        if split:
            stack_body_h = max(1, list_h - 1)
            stack_body_top = list_top + 1
            stack_title_y = list_top
            stack_x = left_w + 1
            stack_body_w = max(1, stack_w - 1)
        else:
            stack_body_h = 0
            stack_body_top = h - 1
            stack_title_y = h - 1 - bottom_stack_h
            stack_x = 0
            stack_body_w = max(1, w - 1)

        if not view:
            hint = (
                "no matches — / to change filter"
                if filter_text
                else "nothing found — l/→ needs a row; try e to browse, or u to go up"
            )
            stdscr.addnstr(
                list_top, 0, _ellipsize(f"  ({hint})", left_w - 1), left_w - 1
            )
        else:
            for i in range(list_h):
                idx = scroll + i
                if idx >= len(view):
                    break
                repo, is_git = view[idx]
                try:
                    is_existing = str(repo.resolve()) in paths_in_ws
                except OSError:
                    is_existing = False
                mark = " ✓ " if is_existing else "[x]" if repo in selected else "[ ]"
                bits = classify_pick(
                    repo,
                    repos=repos,
                    names_in_ws=names_in_ws,
                    paths_in_ws=paths_in_ws,
                    path_ws=path_ws,
                    workspace=workspace,
                )
                bits = [b for b in bits if b != "elsewhere"]
                if repo in selected:
                    bits.append(
                        f"worktree @{branch}" if repo in worktree_paths else "mount"
                    )
                tag = f"  ({' · '.join(bits)})" if bits else ""
                line = f" {mark} {repo.name}{tag}  {repo}"
                attr = curses.A_NORMAL
                if idx == cursor:
                    attr = curses.A_REVERSE
                elif repo in selected:
                    attr |= curses.A_BOLD
                if not is_git and idx != cursor:
                    attr |= curses.color_pair(_COLOR_WARN)
                stdscr.addnstr(
                    list_top + i, 0, _ellipsize(line, left_w - 1), left_w - 1, attr
                )

        if existing_entries:
            stack_title = (
                f" workspace · {len(existing_entries)} connected · {new_n} pending "
            )
        elif already_n:
            stack_title = f" pending · {new_n} new · {already_n} already connected "
        else:
            stack_title = f" pending changes · {mount_n} mount · {worktree_n} worktree "
        title_attr = curses.A_BOLD | curses.color_pair(_COLOR_INFO)

        if split:
            for row in range(list_h):
                y = list_top + row
                try:
                    stdscr.addch(y, left_w, curses.ACS_VLINE)
                except curses.error:
                    stdscr.addnstr(y, left_w, "│", 1)

        stdscr.addnstr(
            stack_title_y,
            stack_x,
            _ellipsize(stack_title, stack_body_w),
            stack_body_w,
            title_attr,
        )

        if split and not selected and not existing_entries:
            empty_attr = curses.A_DIM
            stdscr.addnstr(
                stack_body_top,
                stack_x,
                _ellipsize("(empty — Space on list to pick)", stack_body_w),
                stack_body_w,
                empty_attr,
            )
        elif split:
            panel_lines: list[tuple[str, int]] = []
            for path in selected:
                bits = classify_pick(
                    path,
                    repos=repos,
                    names_in_ws=names_in_ws,
                    paths_in_ws=paths_in_ws,
                    path_ws=path_ws,
                    workspace=workspace,
                )
                bits.append(
                    f"worktree @{branch}" if path in worktree_paths else "mount"
                )
                panel_lines.append(
                    (format_pick_label(path, bits), curses.color_pair(_COLOR_INFO))
                )
            if selected and existing_entries:
                panel_lines.append(
                    (f" already in workspace ({len(existing_entries)})", curses.A_DIM)
                )
            for name, _path in existing_entries:
                panel_lines.append((f" = {name}", curses.A_DIM))
            for i, (line, attr) in enumerate(panel_lines[:stack_body_h]):
                stdscr.addnstr(
                    stack_body_top + i,
                    stack_x,
                    _ellipsize(line, stack_body_w),
                    stack_body_w,
                    attr,
                )

        outside_n = len(selection_outside_scan(selected, repos))
        if message:
            footer = message
        elif selected:
            footer = (
                f"{mount_n} mount · {worktree_n} worktree · Enter applies · Tab reviews"
                + (f" · {outside_n} elsewhere" if outside_n else "")
            )
        elif existing_entries:
            footer = f"{len(existing_entries)} connected · Space adds another project · Tab reviews changes"
        else:
            footer = "Space selects · Enter/→ opens folder · ← goes up · Tab reviews"
        stdscr.addnstr(h - 1, 0, footer.ljust(w - 1)[: w - 1], w - 1, curses.A_REVERSE)
        stdscr.refresh()

    def try_apply(stdscr: Any) -> int | None:
        """Validate and confirm apply. Returns 0 to leave curses, None to stay."""
        nonlocal message
        if not selected:
            message = "will-add stack is empty — Space to pick"
            return None
        if not NAME_RE.match(workspace):
            message = "invalid workspace name"
            return None
        if worktree_paths and not branch.strip():
            message = "branch required for selected worktrees (press b)"
            return None
        conflicts = existing_project_names(config_path, workspace) & {
            p.name for p in selected
        }
        if conflicts and not _confirm_line(
            stdscr,
            f"{len(conflicts)} project(s) already in {workspace!r} "
            f"({', '.join(sorted(conflicts))}) — replace?",
        ):
            message = "apply cancelled (name conflict)"
            return None
        if conflicts:
            args.force = True
        cross = {
            path: ws_name
            for path, ws_name in find_path_conflicts(
                config_path, list(selected)
            ).items()
            if ws_name != workspace
        }
        if cross and not _confirm_line(
            stdscr,
            f"{len(cross)} path(s) already used in other workspace(s) "
            f"({', '.join(sorted(set(cross.values())))}) — mount anyway?",
        ):
            message = "apply cancelled (already used elsewhere)"
            return None
        return 0

    def main_loop(stdscr: Any) -> int:
        nonlocal \
            parent, \
            workspace, \
            use_worktree, \
            branch, \
            cursor, \
            selected, \
            worktree_paths
        nonlocal message, repos, filter_text, depth
        curses.curs_set(0)
        _init_curses_session()

        while True:
            draw(stdscr)
            view = visible_repos()
            key = stdscr.getch()
            if key == curses.KEY_RESIZE:
                continue
            message = ""
            if key == ord("q"):
                return 1
            if key == 27:
                return 1
            if key == 9:  # Tab: full review; Enter there applies.
                message = ""
                names_in_ws, paths_in_ws, path_ws = membership()
                if _review_selection_screen(
                    stdscr,
                    selected,
                    workspace=workspace,
                    repos=repos,
                    names_in_ws=names_in_ws,
                    paths_in_ws=paths_in_ws,
                    path_ws=path_ws,
                    worktree_paths=worktree_paths,
                    branch=branch,
                ):
                    rc_apply = try_apply(stdscr)
                    if rc_apply is not None:
                        return rc_apply
                continue
            if key in (curses.KEY_UP, ord("k")):
                cursor = max(0, cursor - 1)
            elif key in (curses.KEY_DOWN, ord("j")):
                cursor = min(max(0, len(view) - 1), cursor + 1)
            elif key == ord(" "):
                if view:
                    r, _is_git = view[min(cursor, len(view) - 1)]
                    _names, current_paths, _path_ws = membership()
                    try:
                        is_existing = str(r.resolve()) in current_paths
                    except OSError:
                        is_existing = False
                    if is_existing:
                        message = f"{r.name} is already in workspace {workspace!r}"
                    else:
                        toggle_selected(r)
            elif key == ord("a"):
                added: list[Path] = []
                for p, _ in view:
                    if p not in selected:
                        selected.append(p)
                        if use_worktree and is_git_repo(p):
                            worktree_paths.add(p)
                        added.append(p)
                if added:
                    remember_picks(*added)
            elif key == ord("A"):
                selected = []
                worktree_paths = set()
                message = "will-add stack cleared"
            elif key == ord("/"):
                typed = _prompt_line(stdscr, "Filter (empty to clear)", filter_text)
                filter_text = (typed or "").strip()
                cursor = 0
            elif key in (ord("D"), ord("d")):
                depth = 1 if depth >= 2 else 2
                repos = refresh_repos()
                cursor = 0
            elif key in (ord("u"), curses.KEY_BACKSPACE, curses.KEY_LEFT, 127, 8):
                parent = parent.parent
                after_parent_change()
                message = f"up → {parent}"
            elif key in (ord("l"), curses.KEY_RIGHT):
                if not view:
                    message = "nothing to open"
                else:
                    path, _is_git = view[min(cursor, len(view) - 1)]
                    parent = path
                    after_parent_change()
                    message = f"opened {path.name}"
            elif key == ord("?"):
                _show_help(
                    stdscr,
                    "orcan context tui — scan screen",
                    [
                        "Tab      review selected projects; Enter there applies",
                        "Space    toggle highlighted project",
                        "Enter    apply selection; with no picks, open folder",
                        "l / →    open highlighted folder (descend)",
                        "u / ← / Bksp  go up one directory (keeps will-add)",
                        "h        recent picks — Space-add without browsing",
                        "a / A    select all visible / clear will-add stack",
                        "/        filter the list by name",
                        "e        browse jump to another parent",
                        "D        toggle scan depth 1 ↔ 2",
                        "w / t / b  workspace / default for new picks / branch",
                        "Tab + b  switch one selected git project: mount ↔ worktree",
                        "q        quit without applying",
                    ],
                )
            elif key == ord("e"):
                chosen_dir = _browse_dir(stdscr, parent)
                if chosen_dir is not None:
                    parent = chosen_dir
                    after_parent_change()
            elif key == ord("h"):
                now = time.time()
                items: list[tuple[Path, str]] = []
                for hitem in pick_history:
                    if not isinstance(hitem, dict):
                        continue
                    path_s, ts = hitem.get("path"), hitem.get("ts")
                    if not isinstance(path_s, str) or not isinstance(ts, (int, float)):
                        continue
                    age = now - ts
                    if age > PICK_HISTORY_TTL_DAYS * 86400:
                        continue
                    p = Path(path_s)
                    if not p.is_dir():
                        continue
                    try:
                        p = p.resolve()
                    except OSError:
                        continue
                    remaining = PICK_HISTORY_TTL_DAYS * 86400 - age
                    items.append(
                        (p, f"{_humanize(age)} ago · expires in {_humanize(remaining)}")
                    )
                if not items:
                    message = "no recent picks yet — Space-select something first"
                else:
                    jump = _recent_picks_screen(stdscr, items, selected)
                    remember_picks(
                        *[p for p in selected if any(p == it[0] for it in items)]
                    )
                    if jump is not None:
                        parent = jump
                        after_parent_change()
                        message = f"jumped to {parent}"
                    else:
                        message = f"will-add has {len(selected)} path(s)"
            elif key == ord("w"):
                workspace = (
                    _prompt_line(stdscr, "Workspace name", workspace) or workspace
                )
            elif key == ord("t"):
                use_worktree = not use_worktree
                for path in selected:
                    if is_git_repo(path):
                        if use_worktree:
                            worktree_paths.add(path)
                        else:
                            worktree_paths.discard(path)
                message = (
                    "all selected git projects → worktree"
                    if use_worktree
                    else "all selected projects → mount as-is"
                )
            elif key == ord("b"):
                branch = (
                    _prompt_line(stdscr, "Branch for selected worktrees", branch)
                    or branch
                )
            elif key in (curses.KEY_ENTER, 10, 13):
                if selected:
                    rc_apply = try_apply(stdscr)
                    if rc_apply is not None:
                        return rc_apply
                elif view:
                    path, _is_git = view[min(cursor, len(view) - 1)]
                    parent = path
                    after_parent_change()
                    message = f"opened {path.name}"
                else:
                    message = "nothing to open — choose another folder"
        return 1

    rc = curses.wrapper(main_loop)
    if rc != 0:
        info("cancelled")
        return rc

    chosen = list(selected)
    remember_picks(*chosen)
    save_state(
        {
            "last_parent": str(parent.resolve()),
            "last_workspace": workspace,
            "last_branch": branch,
            "last_use_worktree": use_worktree,
            "parent_history": update_parent_history(
                state.get("parent_history") or [], parent
            ),
            "pick_history": pick_history,
        }
    )
    worktree_chosen, mount_chosen = partition_selection_by_mode(chosen, worktree_paths)
    if worktree_chosen:
        apply_selection(
            config_path=config_path,
            workspace=workspace,
            repos=worktree_chosen,
            branch=branch,
            force=bool(args.force),
            start_point=args.start_point,
        )
    if mount_chosen:
        apply_selection(
            config_path=config_path,
            workspace=workspace,
            repos=mount_chosen,
            branch=None,
            force=bool(args.force),
            start_point=args.start_point,
        )
        plain_chosen = [p for p in mount_chosen if not is_git_repo(p)]
        if plain_chosen:
            names = ", ".join(p.name for p in plain_chosen)
            info(
                f"note: {len(plain_chosen)} selected path(s) are not git repos "
                f"({names}) — mounted as-is, no worktree/branch isolation. "
                "Edits there go straight to the shared directory; be careful."
            )
    if args.sync:
        return _run_sync()
    info("Run: orcan sync && orcan down && orcan up")
    return 0


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
    cfg = load_config_or_create(config_path)
    workspaces = cfg.get("workspaces")
    if not isinstance(workspaces, list):
        workspaces = []
        cfg["workspaces"] = workspaces

    state = {
        "dirty": False,
        "cursor": 0,
        "scroll": 0,
        "message": "",
        "collapsed": set(),
    }

    def rows() -> list[tuple[str, int, int | None]]:
        return manage_rows(workspaces, state["collapsed"])

    def draw(stdscr: Any) -> None:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        project_count = sum(
            len([p for p in (ws.get("projects") or []) if isinstance(p, dict)])
            for ws in workspaces
        )
        stdscr.addnstr(0, 0, " orcan init · workspaces ".ljust(w), w, curses.A_REVERSE)
        summary = f" {len(workspaces)} workspace(s) · {project_count} project(s)"
        if state["dirty"]:
            summary += " · unsaved changes"
        stdscr.addnstr(1, 0, _ellipsize(summary, w - 1), w - 1, curses.A_BOLD)
        stdscr.addnstr(
            2,
            0,
            (" ↑↓ choose · ←→ collapse/expand · Enter toggle · a add · n new · ? more")[
                : w - 1
            ],
            w - 1,
            curses.A_DIM,
        )

        current_rows = rows()
        list_top = 4
        list_h = max(1, h - list_top - 2)
        state["scroll"] = min(state["scroll"], state["cursor"])
        if state["cursor"] >= state["scroll"] + list_h:
            state["scroll"] = state["cursor"] - list_h + 1

        if not current_rows:
            stdscr.addnstr(
                list_top,
                0,
                "  (no workspaces — press n to scan a folder)"[: w - 1],
                w - 1,
            )
        else:
            for i in range(list_h):
                idx = state["scroll"] + i
                if idx >= len(current_rows):
                    break
                kind, wi, pi = current_rows[idx]
                ws = workspaces[wi]
                if kind == "ws":
                    n = len(
                        [p for p in (ws.get("projects") or []) if isinstance(p, dict)]
                    )
                    marker = "▸" if wi in state["collapsed"] else "▾"
                    line = f" {marker} {ws.get('name')}  ({n} project{'s' if n != 1 else ''})"
                    attr = curses.A_BOLD
                else:
                    proj = (ws.get("projects") or [])[pi]
                    path_str = str(proj.get("path") or "")
                    is_managed = bool(path_str) and is_under_managed_root(
                        Path(path_str)
                    )
                    tag = " [worktree]" if is_managed else ""
                    line = f"     {proj.get('name')}{tag}  →  {proj.get('path')}"
                    attr = (
                        curses.color_pair(_COLOR_INFO)
                        if is_managed
                        else curses.A_NORMAL
                    )
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
                        _prompt_line(
                            stdscr, "Save before quitting? (y/n/c to cancel)", ""
                        )
                        or ""
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
                state["cursor"] = min(
                    max(0, len(current_rows) - 1), state["cursor"] + 1
                )
                continue
            if key in (curses.KEY_LEFT, curses.KEY_RIGHT):
                if current_rows:
                    kind, wi, _pi = current_rows[state["cursor"]]
                    if kind == "ws":
                        if key == curses.KEY_LEFT:
                            state["collapsed"].add(wi)
                        else:
                            state["collapsed"].discard(wi)
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
                        "↑↓ / j/k  move",
                        "← / →     collapse / expand workspace",
                        "Enter     toggle workspace; rename project",
                        "r         rename workspace or project",
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

            if key in (curses.KEY_ENTER, 10, 13) and kind == "ws":
                if wi in state["collapsed"]:
                    state["collapsed"].discard(wi)
                else:
                    state["collapsed"].add(wi)
                continue
            if key in (ord("r"), curses.KEY_ENTER, 10, 13):
                if kind == "ws":
                    new_name = _prompt_line(
                        stdscr, "Workspace name", str(ws.get("name") or "")
                    )
                    if new_name:
                        err = manage_rename_workspace(workspaces, wi, new_name)
                        if err:
                            state["message"] = err
                        else:
                            state["dirty"] = True
                else:
                    proj = (ws.get("projects") or [])[pi]
                    new_name = _prompt_line(
                        stdscr, "Project name", str(proj.get("name") or "")
                    )
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
                    new_path = _prompt_line(
                        stdscr, "Project path", str(proj.get("path") or "")
                    )
                    if new_path:
                        err = manage_change_project_path(ws, pi, new_path)
                        if err:
                            state["message"] = err
                        else:
                            state["dirty"] = True
            elif key == ord("d"):
                if kind != "proj":
                    state["message"] = (
                        "position on a project to delete it (W deletes a workspace)"
                    )
                else:
                    proj = (ws.get("projects") or [])[pi]
                    if _confirm_line(stdscr, f"Delete project {proj.get('name')!r}?"):
                        path = Path(str(proj.get("path") or ""))
                        is_managed = str(
                            proj.get("path") or ""
                        ) and is_under_managed_root(path)
                        remove_wt = is_managed and _confirm_line(
                            stdscr,
                            "Also remove its managed worktree from disk (git worktree remove)?",
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
                                    remove_worktree(
                                        path, force=True, allow_unmanaged=False
                                    )
                                manifest_remove(
                                    workspace=str(ws.get("name") or ""),
                                    project=str(deleted.get("name") or ""),
                                )
                                state["message"] = (
                                    f"deleted {deleted.get('name')} + worktree"
                                )
                            except SystemExit as exc:
                                state["message"] = (
                                    f"deleted from config; worktree removal failed: {exc}"
                                )
                        else:
                            state["message"] = f"deleted {deleted.get('name')}"
            elif key == ord("W"):
                if _confirm_line(stdscr, f"Delete whole workspace {ws.get('name')!r}?"):
                    managed = managed_projects(ws)
                    remove_wt = managed and _confirm_line(
                        stdscr,
                        f"Also remove {len(managed)} managed worktree(s) from disk?",
                    )
                    if remove_wt:
                        dirty_names = [
                            str(p.get("name"))
                            for p in managed
                            if worktree_is_dirty(Path(str(p["path"])))
                        ]
                        if dirty_names and not _confirm_line(
                            stdscr,
                            f"{len(dirty_names)} of these have UNCOMMITTED CHANGES "
                            f"({', '.join(dirty_names)}) that will be permanently lost — remove anyway?",
                            danger=True,
                        ):
                            remove_wt = False
                    deleted = manage_delete_workspace(workspaces, wi)
                    state["collapsed"].clear()
                    state["dirty"] = True
                    if remove_wt:
                        failures = []
                        for p in managed:
                            path = Path(str(p["path"]))
                            try:
                                if path.exists():
                                    remove_worktree(
                                        path, force=True, allow_unmanaged=False
                                    )
                            except SystemExit as exc:
                                failures.append(f"{p.get('name')}: {exc}")
                        manifest_remove(workspace=str(deleted.get("name") or ""))
                        if failures:
                            state["message"] = (
                                f"deleted workspace {deleted.get('name')}; worktree removal failed: {'; '.join(failures)}"
                            )
                        else:
                            state["message"] = (
                                f"deleted workspace {deleted.get('name')} + {len(managed)} worktree(s)"
                            )
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
    parser.add_argument(
        "--force", action="store_true", help="Replace existing workspace/projects"
    )
    parser.add_argument("--config", default="", help="orcan.config.json path")
    parser.add_argument(
        "--start-point", default="HEAD", help="git worktree start point"
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Run orcan sync after writing config",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=1,
        help="Scan depth under parent (1=children only [default], 2=also grandchildren; TUI: D toggles)",
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
        die(
            "not a TTY — use: orcan context tui --yes --dir DIR --select a,b [--branch NAME]"
        )

    if not args.dir and not args.select:
        existing_path = resolve_config(args.config)
        if existing_path.is_file():
            existing_cfg = load_config(existing_path)
            if (
                isinstance(existing_cfg.get("workspaces"), list)
                and existing_cfg["workspaces"]
            ):
                raise SystemExit(_run_manage(args))

    raise SystemExit(_run_curses(args))


if __name__ == "__main__":
    main()
