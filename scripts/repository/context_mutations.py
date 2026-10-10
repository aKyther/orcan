"""Curses-free configuration mutations shared by context selection and management."""

from __future__ import annotations
from pathlib import Path
from typing import Any

from config_io import die, dump_config, load_config_or_create
from context_selection import NAME_RE
from git_worktrees import find_worktree_by_branch, is_under_managed_root, safe_segment
from managed_workspace import create_managed_workspace, find_workspace

info = print


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

        cfg = load_config_or_create(config_path)
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
            idx = by_name.get(proj_name)
            existing_wt = find_worktree_by_branch(repo, branch_s)
            if idx is not None and existing_wt is not None:
                configured = Path(str(plist[idx].get("path") or "")).resolve()
                if configured == existing_wt.path:
                    info(f"  worktree: {proj_name} (already connected) → {configured}")
                    continue
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
    cfg = load_config_or_create(config_path)
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


def manage_rename_workspace(
    workspaces: list[Any], wi: int, new_name: str
) -> str | None:
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


def manage_change_project_path(
    ws: dict[str, Any], pi: int, new_path: str
) -> str | None:
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
        if (
            isinstance(p, dict)
            and p.get("path")
            and is_under_managed_root(Path(str(p["path"])))
        ):
            out.append(p)
    return out
