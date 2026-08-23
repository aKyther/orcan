#!/usr/bin/env python3
"""orcan migrate — move existing project checkouts under the managed root.

A project path outside the managed root (ORCAN_PROJECTS_ROOT) still needs
its own Compose bind mount, so adding a *sibling* project next to it can
still force a container recreate. Moving it under the managed root once
(this tool) is a one-time cost that removes that project from needing its
own mount ever again — see apply-config.py's managed_projects_root().

Dry-run by default; --yes to actually move. Never touches the source
before the destination move succeeds; a compat symlink is left behind at
the old path by default (disable with --no-symlink).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_io import discover_config, dump_config, load_config  # noqa: E402


def default_managed_root(env: dict) -> Path:
    raw = env.get("ORCAN_PROJECTS_ROOT", "").strip()
    if raw:
        return Path(raw)
    data = env.get("ORCAN_DATA", "").strip() or str(Path.home() / ".config" / "orcan")
    return Path(data) / "sandbox"


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def plan_moves(cfg: dict, managed_root: Path) -> list[tuple[dict, Path, Path]]:
    """[(project_dict, old_path, new_path), …] for every project outside managed_root."""
    moves: list[tuple[dict, Path, Path]] = []
    for ws in cfg.get("workspaces") or []:
        ws_name = str(ws.get("name") or "").strip() or "workspace"
        for project in ws.get("projects") or []:
            path_str = str(project.get("path") or "").strip()
            name = str(project.get("name") or "").strip() or "project"
            if not path_str:
                continue
            old_path = Path(path_str)
            if _is_under(old_path, managed_root):
                continue
            new_path = managed_root / ws_name / name
            moves.append((project, old_path, new_path))
    return moves


def apply_moves(
    moves: list[tuple[dict, Path, Path]], *, leave_symlink: bool
) -> list[str]:
    """Move each project on disk and rewrite its `path` in place. Returns log lines."""
    log: list[str] = []
    for project, old_path, new_path in moves:
        old_resolved = old_path.resolve()
        if not old_resolved.is_dir():
            log.append(f"skip (not a directory): {old_path}")
            continue
        if new_path.exists():
            log.append(f"skip (destination already exists): {new_path}")
            continue
        new_path.parent.mkdir(parents=True, exist_ok=True)
        same_device = old_resolved.stat().st_dev == new_path.parent.stat().st_dev
        shutil.move(str(old_resolved), str(new_path))
        project["path"] = str(new_path)
        log.append(
            f"moved: {old_resolved} -> {new_path}"
            + ("" if same_device else "  (cross-device copy, not an atomic rename)")
        )
        if leave_symlink:
            try:
                old_resolved.symlink_to(new_path, target_is_directory=True)
                log.append(f"  compat symlink left at: {old_resolved}")
            except OSError as exc:
                log.append(f"  warning: could not leave compat symlink at {old_resolved}: {exc}")
    return log


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="", help="Path to orcan.config.json")
    parser.add_argument("--root", default="", help="ORCAN_HOME (config discovery root)")
    parser.add_argument("--managed-root", default="", help="Override ORCAN_PROJECTS_ROOT")
    parser.add_argument("--yes", action="store_true", help="Actually move (default: dry-run)")
    parser.add_argument(
        "--no-symlink", action="store_true", help="Do not leave a compat symlink at the old path"
    )
    args = parser.parse_args()

    import os

    root = Path(args.root or Path.cwd()).resolve()
    config_path = Path(args.config) if args.config else discover_config(root)
    if not config_path or not config_path.is_file():
        print(f"Error: no orcan.config.json found under {root}", file=sys.stderr)
        return 1

    managed_root = (
        Path(args.managed_root) if args.managed_root else default_managed_root(dict(os.environ))
    )

    cfg = load_config(config_path)
    moves = plan_moves(cfg, managed_root)

    if not moves:
        print(f"Nothing to migrate — every project is already under {managed_root}")
        return 0

    print(f"managed root: {managed_root}")
    print(f"{len(moves)} project(s) outside it:")
    for _project, old_path, new_path in moves:
        print(f"  {old_path}  ->  {new_path}")

    if not args.yes:
        print("\nDry-run only — re-run with --yes to actually move them.")
        return 0

    log = apply_moves(moves, leave_symlink=not args.no_symlink)
    for line in log:
        print(line)

    dump_config(config_path, cfg)
    print(f"\nconfig updated: {config_path}")
    print("Next: orcan sync   (then orcan up if the container isn't running yet)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
