#!/usr/bin/env python3
"""Interactive wizard to create or edit orcan.config.json."""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import sys
from pathlib import Path
from typing import Any

try:
    import readline
except ImportError:  # not available on every platform — degrade to plain input()
    readline = None  # type: ignore[assignment]

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
from wizard_ui import (  # noqa: E402
    _yellow,
    ask,
    ask_menu,
    ask_yes_no,
    die,
    heading,
    info,
    success,
    warn,
)

SENSITIVE = {"/", "/home", "/root", "/etc", "/usr", "/var", "/opt"}
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,48}$")


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


def find_cwd_match(cfg: dict[str, Any]) -> tuple[str, str, str] | None:
    """(workspace, project, path) if the current directory is already
    mounted somewhere in cfg — the mirror image of suggest_cwd_project."""
    try:
        cwd = str(Path.cwd().resolve())
    except OSError:
        return None
    for ws in cfg.get("workspaces") or []:
        if not isinstance(ws, dict):
            continue
        ws_name = str(ws.get("name") or "")
        for p in ws.get("projects") or []:
            if isinstance(p, dict) and str(p.get("path") or "") == cwd:
                return ws_name, str(p.get("name") or ""), cwd
    return None


def suggest_cwd_project(cfg: dict[str, Any] | None) -> tuple[str, str] | None:
    """uv/poetry-style default: suggest the current directory as the next
    project, so Enter-Enter accepts it. None if cwd fails the usual path
    checks, or is already mounted somewhere in cfg."""
    err, resolved = validate_project_path(str(Path.cwd()))
    if err or resolved is None:
        return None
    for ws in (cfg or {}).get("workspaces") or []:
        if not isinstance(ws, dict):
            continue
        for p in ws.get("projects") or []:
            if isinstance(p, dict) and str(p.get("path") or "") == str(resolved):
                return None
    return resolved.name, str(resolved)


def ask_name(prompt: str, *, default: str = "", label: str = "name") -> str:
    while True:
        raw = ask(prompt, default or None)
        err = validate_name(raw, label=label)
        if err:
            warn(err)
            continue
        return raw.strip()


def _path_completer(text: str, state: int) -> str | None:
    """Tab-completion for directory paths, readline-style. Directories only
    (a project path is always a directory), ~-prefixes preserved as typed."""
    expanded = os.path.expanduser(text)
    if "/" in expanded:
        list_dir, prefix = expanded.rsplit("/", 1)
        list_dir = list_dir or "/"
    else:
        list_dir, prefix = ".", expanded
    orig_dir = text.rsplit("/", 1)[0] if "/" in text else ""

    try:
        entries = sorted(os.listdir(list_dir))
    except OSError:
        entries = []

    matches = []
    for entry in entries:
        if not entry.startswith(prefix):
            continue
        if not os.path.isdir(os.path.join(list_dir, entry)):
            continue  # a project path is a directory — don't offer plain files
        matches.append(f"{orig_dir}/{entry}/" if orig_dir else f"{entry}/")
    return matches[state] if state < len(matches) else None


@contextlib.contextmanager
def _path_completion():
    """Tab-completes directory paths for the duration of one prompt. No-op if
    readline isn't available (e.g. non-POSIX) — falls back to plain input()."""
    if readline is None:
        yield
        return
    old_delims = readline.get_completer_delims()
    old_completer = readline.get_completer()
    readline.set_completer_delims(" \t\n")  # keep '/' out of delims — complete whole paths
    readline.set_completer(_path_completer)
    readline.parse_and_bind("tab: complete")
    try:
        yield
    finally:
        readline.set_completer(old_completer)
        readline.set_completer_delims(old_delims)


def ask_project_path(
    prompt: str,
    *,
    default: str = "",
    offer_worktrees: bool = True,
) -> str:
    while True:
        with _path_completion():
            raw = ask(prompt, default or None)
        err, resolved = validate_project_path(raw)
        if err:
            warn(err)
            continue
        assert resolved is not None
        if offer_worktrees:
            return maybe_pick_worktree(resolved)
        return str(resolved)


def maybe_pick_worktree(path: Path) -> str:
    """If path is a git repo with extra worktrees, offer to use one of them."""
    try:
        from git_worktrees import format_table, is_git_repo, list_worktrees, resolve_worktree
    except ImportError:
        return str(path)

    if not is_git_repo(path):
        return str(path)
    try:
        trees = list_worktrees(path)
    except SystemExit:
        return str(path)
    if len(trees) <= 1:
        return str(path)

    info("  Existing git worktrees for this repo:")
    info(format_table(trees))
    if not ask_yes_no("  Use one of those worktrees instead?", default=False):
        return str(path)

    while True:
        info("  Pick one of these worktrees:")
        info(format_table(trees))
        raw = ask("  Which worktree? (number, branch, or path)", "2" if len(trees) > 1 else "1")
        try:
            wt = resolve_worktree(path, raw)
        except SystemExit:
            warn("could not resolve that worktree — try again")
            continue
        success(f"  using worktree {wt.path} ({wt.label})")
        return str(wt.path)


def resolve_project_mount(
    source: Path,
    *,
    project_name: str,
    workspace: str,
    prefix: str = "  ",
) -> str:
    """Default: mount the path. Optional advanced help to create/pick a git worktree."""
    try:
        from git_worktrees import (
            format_table,
            is_git_repo,
            is_under_managed_root,
            list_worktrees,
            managed_root,
            resolve_worktree,
        )
    except ImportError:
        return str(source)

    if not is_git_repo(source):
        success(f"{prefix}will mount folder {source}")
        return str(source)

    if is_under_managed_root(source):
        success(f"{prefix}will mount {source}")
        return str(source)

    existing: list = []
    try:
        existing = list_worktrees(source)
    except SystemExit:
        existing = []

    info(f"{prefix}Path: {source}")
    info(f"{prefix}Press Enter to mount it as-is (usual choice).")
    if not ask_yes_no(
        f"{prefix}Create/use a separate git worktree instead?",
        default=False,
    ):
        success(f"{prefix}mounting {source}")
        return str(source)

    info(f"{prefix}Advanced: separate checkout (your clone stays untouched).")
    choices_opts: list[tuple[str, str]] = [
        (
            "create",
            f"new worktree at {managed_root(ensure=False)}/{workspace}/{project_name}/",
        ),
        ("cancel", "never mind — mount the path above"),
    ]
    if len(existing) > 1:
        info(f"{prefix}Existing worktrees:")
        info(format_table(existing))
        choices_opts.insert(1, ("pick", "use one of the existing worktrees"))

    action = ask_menu(f"{prefix}Worktree options:", choices_opts, default="create")
    if action == "cancel":
        success(f"{prefix}mounting {source}")
        return str(source)

    if action == "pick":
        while True:
            info(f"{prefix}Pick one of these worktrees:")
            info(format_table(existing))
            raw = ask(
                f"{prefix}Which worktree? (number, branch, or path)",
                "2" if len(existing) > 1 else "1",
            )
            try:
                wt = resolve_worktree(source, raw)
            except SystemExit:
                warn("could not resolve — try again")
                continue
            success(f"{prefix}using {wt.path} ({wt.label})")
            return str(wt.path)

    return _create_worktree_with_retry(
        source,
        project_name=project_name,
        workspace=workspace,
        prefix=prefix,
    )


def _offer_pull_before_worktree(source: Path, *, prefix: str) -> None:
    """A new worktree branches from source's current HEAD (create_worktree's
    default start_point) — offer to fast-forward that branch first, so HEAD
    isn't a stale local master. Silent no-op on detached HEAD; otherwise
    always asks (default yes) rather than pulling without confirmation."""
    from git_worktrees import current_branch, pull_current_branch

    branch = current_branch(source)
    if not branch:
        return
    if not ask_yes_no(
        f"{prefix}Pull latest {branch!r} in {source} before branching the worktree?",
        default=True,
    ):
        return
    ok, msg = pull_current_branch(source)
    if ok:
        success(f"{prefix}{branch}: {msg}")
    else:
        warn(f"{prefix}skipped pull ({branch!r}): {msg}")


def _create_worktree_with_retry(
    source: Path,
    *,
    project_name: str,
    workspace: str,
    prefix: str,
) -> str:
    """Ask for a branch, create managed worktree; on conflict offer retry / use / cancel."""
    from git_worktrees import (
        WorktreeCreateError,
        branch_exists,
        create_worktree,
        find_worktree_by_branch,
    )

    _offer_pull_before_worktree(source, prefix=prefix)

    default_branch = project_name
    while True:
        branch = ask(f"{prefix}Branch name for the new worktree", default_branch).strip()
        if not branch:
            warn("empty branch name")
            if ask_yes_no(f"{prefix}Mount the original folder instead?", default=True):
                success(f"{prefix}mounting {source}")
                return str(source)
            continue

        in_use = find_worktree_by_branch(source, branch)
        if in_use is not None:
            warn(f"{prefix}Branch {branch!r} is already checked out at:")
            info(f"{prefix}  {in_use.path}")
            choice = ask_menu(
                f"{prefix}What next?",
                [
                    ("use", "use that existing worktree"),
                    ("retry", "try a different branch name"),
                    ("cancel", "mount the original folder instead"),
                ],
                default="use",
            )
            if choice == "use":
                success(f"{prefix}using {in_use.path} ({in_use.label})")
                return str(in_use.path)
            if choice == "cancel":
                success(f"{prefix}mounting {source}")
                return str(source)
            default_branch = f"{branch}-2"
            continue

        if branch_exists(source, branch):
            info(
                f"{prefix}Branch {branch!r} already exists (free) — "
                "will attach a new worktree to it."
            )
        else:
            info(f"{prefix}Will create new branch {branch!r} from HEAD.")

        info(f"{prefix}Creating worktree…")
        try:
            wt = create_worktree(
                source,
                branch=branch,
                workspace=workspace,
                project=project_name,
                managed=True,
                fatal=False,
            )
        except WorktreeCreateError as exc:
            warn(f"{prefix}{exc}")
            if exc.hint:
                info(f"{prefix}{exc.hint}")
            opts: list[tuple[str, str]] = [
                ("retry", "try a different branch name"),
                ("cancel", "mount the original folder instead"),
            ]
            default = "retry"
            if exc.existing is not None:
                opts.insert(0, ("use", f"use existing path {exc.existing.path}"))
                default = "use"
            choice = ask_menu(f"{prefix}What next?", opts, default=default)
            if choice == "use" and exc.existing is not None:
                success(f"{prefix}using {exc.existing.path}")
                return str(exc.existing.path)
            if choice == "cancel":
                success(f"{prefix}mounting {source}")
                return str(source)
            default_branch = f"{branch}-2" if not branch.endswith("-2") else f"{branch}b"
            continue

        success(f"{prefix}worktree ready: {wt.path}")
        return str(wt.path)


def ask_project(
    *,
    default_name: str = "",
    default_path: str = "",
    workspace: str = "",
    another: bool = False,
) -> dict[str, str]:
    prefix = "  "
    ws = workspace or "workspace"
    info()
    if another:
        info(_yellow(f"{prefix}› Another project for workspace {ws!r}"))
    else:
        info(_yellow(f"{prefix}› Project for workspace {ws!r}"))
    path = ask_project_path(
        f"{prefix}Project path (absolute, e.g. /home/you/code/api)",
        default=default_path,
        offer_worktrees=False,
    )
    default_name = default_name or Path(path).name
    info(f"{prefix}Label for this folder (not the workspace name).")
    name = ask_name(
        f"{prefix}Project name",
        default=default_name,
        label="project name",
    )
    final_path = resolve_project_mount(
        Path(path),
        project_name=name,
        workspace=ws,
        prefix=prefix,
    )
    success(f"{prefix}project {name!r} → {final_path}")
    return {"name": name, "path": final_path}


def ask_new_workspace(*, another: bool = False, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Collect one workspace: a name + project paths (worktree optional per project)."""
    if another:
        heading("Another workspace")
    else:
        heading("New workspace")
    suggestion = suggest_cwd_project(cfg)
    info("  Workspace = name for this whole set of folders (e.g. myapp, client-a).")
    if suggestion:
        info(f"  Detected current directory ({suggestion[1]}) — suggested below, Enter to accept.")
    name = ask_name(
        "  Workspace name",
        default=suggestion[0] if suggestion else "",
        label="workspace name",
    )
    projects: list[dict[str, str]] = []
    info(f"  Workspace {name!r} is set. Next: add project folders into it.")
    info("  Tip: Enter accepts defaults; you need at least one project.")
    while True:
        if projects:
            info(f"  So far in workspace {name!r}:")
            for p in projects:
                info(f"    • {p['name']} → {p['path']}")
            if not ask_yes_no(f"  Add another project to workspace {name!r}?", default=False):
                break
            projects.append(ask_project(workspace=name, another=True))
        else:
            projects.append(
                ask_project(
                    workspace=name,
                    another=False,
                    default_path=suggestion[1] if suggestion else "",
                )
            )
    success(f"  workspace {name!r} has {len(projects)} project(s)")
    return {"name": name, "projects": projects}


def summarize(cfg: dict[str, Any], *, title: str = "Summary") -> None:
    workspaces = cfg.get("workspaces") or []
    info()
    info(f"── {title} ──")
    if not workspaces:
        info("  (no workspaces)")
        return
    try:
        from git_worktrees import is_under_managed_root
    except ImportError:
        def is_under_managed_root(_p: Path) -> bool:  # type: ignore[misc]
            return False

    for ws in workspaces:
        if not isinstance(ws, dict):
            continue
        info(f"  • workspace {ws.get('name', '?')}")
        for p in ws.get("projects") or []:
            if isinstance(p, dict):
                path = str(p.get("path") or "")
                tag = " (worktree)" if is_under_managed_root(Path(path)) else ""
                info(f"      • {p.get('name')}  →  {path}{tag}")
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


def edit_project(
    proj: dict[str, Any],
    *,
    workspace: str = "",
) -> dict[str, Any] | None:
    info(f"  • {proj.get('name')}  →  {proj.get('path')}")
    action = ask_menu(
        "",
        [
            ("keep", "keep this project"),
            ("change", "change path / name"),
            ("delete", "remove from workspace"),
        ],
        default="keep",
    )
    if action == "keep":
        return dict(proj)
    if action == "delete":
        return None
    return ask_project(
        default_name=str(proj.get("name") or ""),
        default_path=str(proj.get("path") or ""),
        workspace=workspace or str(proj.get("name") or "workspace"),
        another=False,
    )


def ask_more_projects(
    name: str,
    projects: list[dict[str, str]],
) -> list[dict[str, str]]:
    while ask_yes_no(f"  Add another project to workspace {name!r}?", default=False):
        projects.append(ask_project(workspace=name, another=True))
    return projects


def edit_workspace(ws: dict[str, Any]) -> dict[str, Any] | None:
    info()
    heading(f"Workspace {ws.get('name')!r}")
    for p in ws.get("projects") or []:
        if isinstance(p, dict):
            info(f"    • {p.get('name')} → {p.get('path')}")
    action = ask_menu(
        "",
        [
            ("keep", "keep as-is (optionally add projects)"),
            ("change", "rename / edit projects"),
            ("delete", "remove this workspace from config"),
        ],
        default="keep",
    )
    if action == "delete":
        return None

    name = str(ws.get("name") or "")
    if action == "keep":
        projects_out = [
            dict(p) for p in (ws.get("projects") or []) if isinstance(p, dict)
        ]
        ask_more_projects(name, projects_out)
        return {"name": name, "projects": projects_out}

    name = ask_name(
        "  Workspace name",
        default=name,
        label="workspace name",
    )
    projects_out: list[dict[str, str]] = []
    for proj in ws.get("projects") or []:
        if not isinstance(proj, dict):
            continue
        edited = edit_project(proj, workspace=name)
        if edited is not None:
            projects_out.append(edited)
    ask_more_projects(name, projects_out)
    if not projects_out:
        warn("workspace needs at least one project")
        if ask_yes_no("  Add a project now?", default=True):
            projects_out.append(ask_project(workspace=name, another=False))
            ask_more_projects(name, projects_out)
        else:
            warn("dropping empty workspace")
            return None
    return {"name": name, "projects": projects_out}


def edit_existing(cfg: dict[str, Any]) -> dict[str, Any]:
    summarize(cfg, title="Current workspaces")
    heading("Review each workspace")
    info("For each one: keep (Enter), change, or delete.")
    new_workspaces: list[dict[str, Any]] = []
    for ws in cfg.get("workspaces") or []:
        if not isinstance(ws, dict):
            continue
        edited = edit_workspace(ws)
        if edited is not None:
            new_workspaces.append(edited)
    heading("Add more?")
    while ask_yes_no("Add another workspace?", default=False):
        created = ask_new_workspace(another=True, cfg={"workspaces": new_workspaces})
        new_workspaces.append(created)
    if not new_workspaces:
        die("need at least one workspace — nothing saved")
    out = dict(cfg)
    out["workspaces"] = new_workspaces
    return out


def print_orientation() -> None:
    info("Quick map:")
    info("  workspace = name for a group of folders (asked first)")
    info("  project   = one folder path + its short label (asked per folder)")
    info("  worktree  = optional separate git checkout (say n unless you need it)")


def print_next_steps() -> None:
    info()
    info("Next (apply + open terminal):")
    info("  orcan sync")
    info("  orcan down && orcan up")
    info("Then open the URL printed by orcan up (default http://localhost:7681).")


def create_fresh() -> dict[str, Any]:
    info("No config yet — creating your first workspace.")
    print_orientation()
    cfg: dict[str, Any] = {"workspaces": []}
    cfg["workspaces"].append(ask_new_workspace(another=False, cfg=cfg))
    while ask_yes_no("Add another workspace?", default=False):
        cfg["workspaces"].append(ask_new_workspace(another=True, cfg=cfg))
    # tmux/ttyd are tool settings, not workspace data — seed defaults here;
    # customize later with `orcan settings`.
    cfg["tmux"] = {"initial_windows": 3, "window_prefix": "tab"}
    cfg["ttyd"] = {
        "port": 7681,
        "host_port": 7681,
        "font_size": 19,
        "font_family": "Menlo, Monaco, 'Courier New', monospace",
        "theme": "dark",
        "ping_interval": 20,
    }
    info()
    info("  ✓ tmux/ttyd: using defaults (customize later: orcan settings)")
    return cfg


def find_workspace_name(cfg: dict[str, Any], name: str) -> bool:
    for ws in cfg.get("workspaces") or []:
        if isinstance(ws, dict) and ws.get("name") == name:
            return True
    return False


def wizard_remove_managed_worktrees(cfg: dict[str, Any], config_path: Path) -> dict[str, Any]:
    from managed_workspace import remove_managed_workspace
    from git_worktrees import is_under_managed_root, load_manifest, managed_root

    heading("Clean managed worktrees")
    info(f"Only under: {managed_root(ensure=False)}")
    info("(Does not delete your normal clones — only checkouts Orcan created here.)")
    entries = load_manifest()
    by_ws: dict[str, int] = {}
    for e in entries:
        by_ws[e.workspace] = by_ws.get(e.workspace, 0) + 1

    for ws in cfg.get("workspaces") or []:
        if not isinstance(ws, dict):
            continue
        name = str(ws.get("name") or "")
        if not name or name in by_ws:
            continue
        for p in ws.get("projects") or []:
            if isinstance(p, dict) and is_under_managed_root(Path(str(p.get("path") or ""))):
                by_ws[name] = by_ws.get(name, 0) + 1

    if not by_ws:
        info("  Nothing to clean.")
        return cfg

    names = sorted(by_ws)
    for i, name in enumerate(names, 1):
        info(f"  {i}) {name}  — {by_ws[name]} worktree(s)")
    raw = ask("Number to clean up", "1")
    try:
        ws_name = names[int(raw) - 1]
    except (ValueError, IndexError):
        warn("invalid choice")
        return cfg

    if not ask_yes_no(
        f"Remove managed worktrees for {ws_name!r} from disk and config?",
        default=False,
    ):
        info("Cancelled.")
        return cfg

    force = ask_yes_no("Force if the worktree has uncommitted changes?", default=False)
    remove_managed_workspace(
        config_path=config_path,
        workspace=ws_name,
        force=force,
        keep_config=False,
    )
    success(f"cleaned {ws_name!r}")
    return load_config(config_path)


def top_menu(cfg: dict[str, Any], config_path: Path) -> dict[str, Any]:
    heading("What do you want to do?")
    action = ask_menu(
        "",
        [
            ("add", "add a workspace (mount project folders)"),
            ("edit", "change existing workspaces"),
            ("clean", "remove worktrees Orcan created under $ORCAN_DATA/worktrees"),
        ],
        default="add",
    )
    if action == "add":
        created = ask_new_workspace(another=bool(cfg.get("workspaces")), cfg=cfg)
        ws_name = str(created.get("name") or "")
        workspaces = [
            ws
            for ws in (cfg.get("workspaces") or [])
            if not (isinstance(ws, dict) and ws.get("name") == ws_name)
        ]
        if find_workspace_name(cfg, ws_name):
            if not ask_yes_no(f"Workspace {ws_name!r} already exists — replace it?", default=False):
                info("Cancelled.")
                return cfg
        workspaces.append(created)
        out = dict(cfg)
        out["workspaces"] = workspaces
        return out
    if action == "edit":
        return edit_existing(cfg)
    return wizard_remove_managed_worktrees(cfg, config_path)


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
    print_orientation()
    info()

    if args.config:
        existing = Path(args.config)
        if not existing.is_absolute():
            existing = (root / existing).resolve()
        if not existing.is_file():
            die(f"config not found: {existing}")
    else:
        existing = discover_config(root)

    if existing and existing.is_file():
        info(f"Config file: {existing}")
        cfg = load_config(existing)
        match = find_cwd_match(cfg)
        if match:
            ws_name, proj_name, cwd_path = match
            success(
                f"this directory is already configured: "
                f"workspace {ws_name!r}, project {proj_name!r} ({cwd_path})"
            )
            if not ask_yes_no("Change anything?", default=False):
                info("Nothing to do here — orcan init still runs sync next.")
                return
            info()
        summarize(cfg, title="What you have now")
        cfg = top_menu(cfg, existing)
        out_path = existing
        ensure_unique_names(cfg)
        summarize(cfg, title="Review")
        info()
        info(f"Save to: {out_path}")
        if not ask_yes_no("Save these changes?", default=True):
            info("Cancelled — nothing written (unless you used clean).")
            return
        dump_config(out_path, cfg)
        info()
        success(f"saved {out_path}")
        print_next_steps()
        return

    cfg = create_fresh()
    out_path = default_write_path(root)

    ensure_unique_names(cfg)
    summarize(cfg, title="Review")
    info()
    info(f"Will create: {out_path}")
    if not ask_yes_no("Save?", default=True):
        info("Cancelled — nothing written.")
        return

    dump_config(out_path, cfg)
    info()
    success(f"saved {out_path}")
    print_next_steps()


if __name__ == "__main__":
    main()
