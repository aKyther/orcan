#!/usr/bin/env python3
"""Create / remove a workspace backed by managed git worktrees under $ORCAN_PROJECTS_ROOT/.worktrees.

Used by the config wizard (clean) and tests. Public CLI: orcan context worktree …
(and wizard) — not a separate product surface.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("ORCAN_HOME") or Path(__file__).resolve().parents[2])
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_io import (  # noqa: E402
    default_write_path,
    die,
    discover_config,
    dump_config,
    find_workspace,
    load_config,
)
from git_worktrees import (  # noqa: E402
    create_worktree,
    is_git_repo,
    load_manifest,
    managed_root,
    managed_worktree_path,
    manifest_remove,
    manifest_upsert,
    remove_worktree,
    safe_segment,
    is_under_managed_root,
    ManifestEntry,
)


def info(msg: str = "") -> None:
    print(msg)


def resolve_config(path: str) -> Path:
    if path:
        p = Path(path)
        if not p.is_absolute():
            p = (ROOT / p).resolve()
        return p
    return discover_config(ROOT) or default_write_path(ROOT)


def parse_project_specs(specs: list[str]) -> list[tuple[str, Path]]:
    """Parse name=/abs/path specs."""
    out: list[tuple[str, Path]] = []
    for spec in specs:
        if "=" not in spec:
            die(f"project must be name=/absolute/path (got: {spec})")
        name, _, path_s = spec.partition("=")
        name = name.strip()
        path = Path(path_s.strip())
        if not name:
            die(f"empty project name in {spec}")
        if not path.is_absolute():
            die(f"project path must be absolute: {path}")
        if not path.is_dir():
            die(f"project path does not exist: {path}")
        if not is_git_repo(path):
            die(f"not a git repository: {path}")
        out.append((safe_segment(name, label="project"), path.resolve()))
    if not out:
        die("need at least one --project name=/abs/path")
    return out


def create_managed_workspace(
    *,
    config_path: Path,
    workspace: str,
    branch: str,
    projects: list[tuple[str, Path]],
    start_point: str = "HEAD",
    force: bool = False,
) -> dict[str, Any]:
    """Create managed worktrees for each project and pin them as one workspace."""
    ws_name = safe_segment(workspace, label="workspace")
    branch = branch.strip()
    if not branch:
        die("branch is empty")

    if config_path.is_file():
        cfg = load_config(config_path)
    else:
        cfg = {"workspaces": []}
    cfg.setdefault("workspaces", [])
    if not isinstance(cfg["workspaces"], list):
        die("workspaces must be an array")

    existing = find_workspace(cfg, ws_name)
    if existing is not None and not force:
        die(f"workspace {ws_name!r} already exists; use --force to replace")

    # Projects unchanged from the existing workspace already have a worktree
    # at this exact (deterministic) managed path — reuse it instead of
    # re-running `git worktree add`, which would just die on "already exists".
    existing_paths: dict[str, str] = {}
    if existing is not None:
        for p in existing.get("projects") or []:
            if isinstance(p, dict) and p.get("name"):
                existing_paths[str(p["name"])] = str(p.get("path") or "")

    created: list[dict[str, str]] = []
    for proj_name, repo in projects:
        expected = managed_worktree_path(ws_name, proj_name)
        reuse_path = existing_paths.get(proj_name)

        if reuse_path:
            reuse = Path(reuse_path)
            if reuse.exists() and reuse.resolve() == expected.resolve():
                info(f"  worktree: {proj_name} (unchanged) → {reuse_path}")
                created.append({"name": proj_name, "path": reuse_path})
                continue

        if force and reuse_path:
            old = Path(reuse_path)
            if (
                old.exists()
                and old.resolve() != expected.resolve()
                and is_under_managed_root(old)
            ):
                info(f"  removing superseded managed worktree: {proj_name} ← {old}")
                remove_worktree(old, force=True, allow_unmanaged=False)
                manifest_remove(workspace=ws_name, project=proj_name)

        if expected.exists() and is_git_repo(expected):
            info(f"  worktree: {proj_name} (exists) → {expected}")
            created.append({"name": proj_name, "path": str(expected)})
            manifest_upsert(
                ManifestEntry(
                    workspace=ws_name,
                    project=proj_name,
                    repo=str(repo.resolve()),
                    path=str(expected),
                    branch=branch,
                )
            )
            continue

        info(f"  worktree: {proj_name} ← {repo} @ {branch}")
        wt = create_worktree(
            repo,
            branch=branch,
            start_point=start_point,
            workspace=ws_name,
            project=proj_name,
            managed=True,
        )
        created.append({"name": proj_name, "path": str(wt.path)})

    ws_obj = {"name": ws_name, "projects": created}
    if existing is not None:
        # force=True is guaranteed here (die above otherwise) — clean up
        # worktrees for projects dropped or renamed out of this workspace so
        # they don't linger as orphans under $ORCAN_PROJECTS_ROOT/.worktrees.
        new_names = {name for name, _ in projects}
        for old_proj in existing.get("projects") or []:
            if not isinstance(old_proj, dict):
                continue
            old_name = old_proj.get("name")
            if not old_name or old_name in new_names:
                continue
            old_path = Path(str(old_proj.get("path") or ""))
            info(f"  removing dropped worktree: {old_name} ← {old_path}")
            if old_path and old_path.exists():
                remove_worktree(old_path, force=True, allow_unmanaged=False)
            else:
                info("    (already missing on disk)")
            manifest_remove(workspace=ws_name, project=str(old_name))
        for i, ws in enumerate(cfg["workspaces"]):
            if isinstance(ws, dict) and ws.get("name") == ws_name:
                cfg["workspaces"][i] = ws_obj
                break
    else:
        cfg["workspaces"].append(ws_obj)

    dump_config(config_path, cfg)
    info(f"workspace {ws_name!r}: {len(created)} managed worktree(s)")
    info(f"managed root: {managed_root()}")
    info(f"config: {config_path}")
    info("Next: orcan sync  (worktrees under sandbox — no container recreate)")
    return cfg


def remove_managed_workspace(
    *,
    config_path: Path,
    workspace: str,
    force: bool = False,
    keep_config: bool = False,
) -> None:
    """Remove managed worktrees for a workspace (and optionally the config entry)."""
    ws_name = safe_segment(workspace, label="workspace")
    entries = [e for e in load_manifest() if e.workspace == ws_name]
    if not entries:
        if config_path.is_file():
            cfg = load_config(config_path)
            ws = find_workspace(cfg, ws_name)
            if ws:
                for p in ws.get("projects") or []:
                    if isinstance(p, dict) and p.get("path"):
                        from git_worktrees import ManifestEntry, is_under_managed_root

                        path = Path(str(p["path"]))
                        if is_under_managed_root(path):
                            entries.append(
                                ManifestEntry(
                                    workspace=ws_name,
                                    project=str(p.get("name") or path.name),
                                    repo="",
                                    path=str(path),
                                    branch="",
                                )
                            )
        if not entries:
            die(f"no managed worktrees recorded for workspace {ws_name!r}")

    info(f"Removing {len(entries)} managed worktree(s) for {ws_name!r}:")
    for e in entries:
        info(f"  - {e.project}: {e.path}")
        path = Path(e.path)
        if path.exists():
            remove_worktree(path, force=force, allow_unmanaged=False)
        else:
            info("    (already missing on disk)")

    manifest_remove(workspace=ws_name)

    if keep_config or not config_path.is_file():
        info("config left unchanged")
        return

    cfg = load_config(config_path)
    before = cfg.get("workspaces") or []
    cfg["workspaces"] = [
        ws
        for ws in before
        if not (isinstance(ws, dict) and ws.get("name") == ws_name)
    ]
    dump_config(config_path, cfg)
    info(f"removed workspace {ws_name!r} from {config_path}")
    info("Next: orcan sync  (worktrees under sandbox — no container recreate)")


def list_managed_workspaces() -> None:
    entries = load_manifest()
    root = managed_root()
    info(f"managed worktrees under {root}")
    if not entries:
        info("  (none)")
        return
    by_ws: dict[str, list] = {}
    for e in entries:
        by_ws.setdefault(e.workspace, []).append(e)
    for ws, items in sorted(by_ws.items()):
        info(f"  {ws}/")
        for e in items:
            info(f"    • {e.project}  ({e.branch})  →  {e.path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_c = sub.add_parser("create", help="Create managed worktrees + workspace")
    p_c.add_argument("--config", default="")
    p_c.add_argument("--workspace", required=True)
    p_c.add_argument("--branch", required=True)
    p_c.add_argument(
        "--project",
        action="append",
        default=[],
        help="Repeatable: name=/absolute/path/to/main/checkout",
    )
    p_c.add_argument("--start-point", default="HEAD")
    p_c.add_argument("--force", action="store_true")

    p_r = sub.add_parser("remove", help="Remove managed worktrees + workspace entry")
    p_r.add_argument("--config", default="")
    p_r.add_argument("--workspace", required=True)
    p_r.add_argument("--force", action="store_true")
    p_r.add_argument(
        "--keep-config",
        action="store_true",
        help="Only remove worktrees; leave orcan.config.json alone",
    )

    p_l = sub.add_parser("list", help="List managed worktrees")

    args = parser.parse_args()
    if args.cmd == "list":
        list_managed_workspaces()
        return
    if args.cmd == "create":
        create_managed_workspace(
            config_path=resolve_config(args.config),
            workspace=args.workspace,
            branch=args.branch,
            projects=parse_project_specs(args.project),
            start_point=args.start_point,
            force=bool(args.force),
        )
        return
    if args.cmd == "remove":
        remove_managed_workspace(
            config_path=resolve_config(args.config),
            workspace=args.workspace,
            force=bool(args.force),
            keep_config=bool(args.keep_config),
        )
        return


if __name__ == "__main__":
    main()
