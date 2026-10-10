"""Directory discovery and selection models, without terminal rendering."""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Any

from config_io import die, load_config
from context_presenters import _ellipsize, format_pick_label
from git_worktrees import is_git_repo
from managed_workspace import find_workspace

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,48}$")
HISTORY_LIMIT = 8
HISTORY_TTL_DAYS = 3.0
PICK_HISTORY_LIMIT = 16
PICK_HISTORY_TTL_DAYS = 14.0


def scan_dirs(parent: Path, *, max_depth: int = 1) -> list[tuple[Path, bool]]:
    """Find git repos AND plain directories under parent (depth 1 = children only,
    2 = also grandchildren of non-repo children). Each entry is (path, is_git) —
    plain dirs are still selectable (mount as-is only; no managed worktree,
    since that needs a git repo to branch from). Default is first level so a
    large tree stays scannable; use depth 2 or browse into a child when needed."""
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
                (
                    p
                    for p in child.iterdir()
                    if p.is_dir() and not p.name.startswith(".")
                ),
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


def scan_repos(parent: Path, *, max_depth: int = 1) -> list[Path]:
    """Git repos only under parent — thin filter over scan_dirs(), kept for
    the --yes/--select non-interactive path."""
    return [p for p, is_git in scan_dirs(parent, max_depth=max_depth) if is_git]


def workspace_membership(
    config_path: Path, workspace: str
) -> tuple[set[str], set[str]]:
    """Project names and resolved paths already registered in `workspace`.
    Empty sets when the config / workspace is missing. Pure/curses-free."""
    if not config_path.is_file():
        return set(), set()
    cfg = load_config(config_path)
    ws = find_workspace(cfg, workspace)
    if not ws:
        return set(), set()
    names: set[str] = set()
    paths: set[str] = set()
    for p in ws.get("projects") or []:
        if not isinstance(p, dict):
            continue
        name = p.get("name")
        if name:
            names.add(str(name))
        raw = str(p.get("path") or "").strip()
        if not raw:
            continue
        try:
            paths.add(str(Path(raw).expanduser().resolve()))
        except OSError:
            paths.add(raw)
    return names, paths


def workspace_project_entries(
    config_path: Path, workspace: str
) -> list[tuple[str, Path]]:
    """Configured projects in workspace order, for an add-project preview."""
    if not config_path.is_file():
        return []
    cfg = load_config(config_path)
    ws = find_workspace(cfg, workspace)
    if not ws:
        return []
    out: list[tuple[str, Path]] = []
    for project in ws.get("projects") or []:
        if not isinstance(project, dict):
            continue
        raw = str(project.get("path") or "").strip()
        if not raw:
            continue
        try:
            path = Path(raw).expanduser().resolve()
        except OSError:
            path = Path(raw)
        out.append((str(project.get("name") or path.name), path))
    return out


def classify_pick(
    path: Path,
    *,
    repos: list[tuple[Path, bool]],
    names_in_ws: set[str],
    paths_in_ws: set[str],
    path_ws: dict[str, str],
    workspace: str,
) -> list[str]:
    """Short status tags for a pick in the scan list or will-add stack."""
    visible = {p for p, _ in repos}
    git_by_path = {p: is_git for p, is_git in repos}
    is_git = git_by_path.get(path)
    if is_git is None:
        is_git = is_git_repo(path)
    try:
        resolved = str(path.resolve())
    except OSError:
        resolved = str(path)

    bits: list[str] = []
    if not is_git:
        bits.append("mount")
    if path not in visible:
        bits.append("elsewhere")
    if resolved in paths_in_ws:
        bits.append("in ws")
    elif path.name in names_in_ws:
        bits.append("name taken")
    other = path_ws.get(resolved)
    if other and other != workspace:
        bits.append("other ws")
    return bits


def format_will_add_lines(
    selected: list[Path],
    repos: list[tuple[Path, bool]],
    *,
    width: int,
    max_lines: int,
    names_in_ws: set[str] | None = None,
    paths_in_ws: set[str] | None = None,
    path_ws: dict[str, str] | None = None,
    workspace: str = "",
) -> list[str]:
    """Body lines for the 'will add' stack (pick order). Pure/curses-free.

    Each line is ellipsized to width. When there are more picks than max_lines,
    the last line is a '+N more' summary. Empty selection yields one hint line.
    """
    if width <= 0 or max_lines <= 0:
        return []
    if not selected:
        return [_ellipsize("(empty — Space to pick)", width)]

    names_in_ws = names_in_ws or set()
    paths_in_ws = paths_in_ws or set()
    path_ws = path_ws or {}
    lines: list[str] = []
    show = selected
    omitted = 0
    if len(selected) > max_lines:
        show = selected[: max_lines - 1]
        omitted = len(selected) - len(show)

    for path in show:
        bits = classify_pick(
            path,
            repos=repos,
            names_in_ws=names_in_ws,
            paths_in_ws=paths_in_ws,
            path_ws=path_ws,
            workspace=workspace,
        )
        lines.append(_ellipsize(format_pick_label(path, bits), width))

    if omitted:
        lines.append(_ellipsize(f"… +{omitted} more", width))
    return lines


def selection_mode_summary(
    selected: list[Path], worktree_paths: set[Path]
) -> tuple[int, int]:
    """Return (mount_as_is, worktree) counts for the pending selection."""
    worktrees = sum(path in worktree_paths for path in selected)
    return len(selected) - worktrees, worktrees


def partition_selection_by_mode(
    selected: list[Path], worktree_paths: set[Path]
) -> tuple[list[Path], list[Path]]:
    """Return (worktree_paths, mount_as_is_paths), preserving pick order."""
    worktrees = [
        path for path in selected if path in worktree_paths and is_git_repo(path)
    ]
    mounts = [path for path in selected if path not in worktrees]
    return worktrees, mounts


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


def update_pick_history(
    existing: list[Any],
    paths: list[Path],
    *,
    limit: int = PICK_HISTORY_LIMIT,
    ttl_days: float = PICK_HISTORY_TTL_DAYS,
    now: float | None = None,
) -> list[dict[str, Any]]:
    """Remember recently picked project/dir paths (newest first).
    Last path in `paths` becomes the newest entry. Pure/curses-free."""
    now = time.time() if now is None else now
    hist = existing
    for path in paths:
        hist = update_parent_history(
            hist, path, limit=limit, ttl_days=ttl_days, now=now
        )
    return hist


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
