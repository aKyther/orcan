#!/usr/bin/env python3
"""Delete Orcan config/data while preserving project checkout roots."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from path_guards import is_sensitive_path


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _absolute(path: Path) -> Path:
    return path.expanduser().absolute()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _validate_target(path: Path) -> Path:
    resolved = _resolved(path)
    home = Path.home().resolve()
    if resolved == home or is_sensitive_path(resolved):
        raise ValueError(f"refusing unsafe purge target: {path} -> {resolved}")
    if path.is_symlink():
        raise ValueError(
            f"refusing symlink purge target: {path} -> {resolved}; "
            "point ORCAN_HOME/ORCAN_DATA at the real directory and retry"
        )
    return resolved


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path)


def _purge_branch(path: Path, protected: tuple[tuple[Path, Path], ...]) -> bool:
    """Purge *path*; return True when some protected subtree was retained."""
    absolute = _absolute(path)
    resolved = _resolved(path)
    if any(absolute == logical or resolved == real for logical, real in protected):
        return True

    descendants = tuple(
        keep
        for keep in protected
        if _is_within(keep[0], absolute) or _is_within(keep[1], resolved)
    )
    if not descendants:
        _remove(path)
        return False

    # Following a symlink while selectively deleting could modify an
    # unexpected external tree. Preserve that whole symlink branch instead.
    if path.is_symlink():
        return True

    if not path.is_dir():
        _remove(path)
        return False

    kept = False
    for child in tuple(path.iterdir()):
        kept = _purge_branch(child, descendants) or kept
    if not kept:
        path.rmdir()
    return kept


def purge_targets(targets: list[Path], protected: list[Path]) -> list[Path]:
    """Purge targets and return protected roots that still exist."""
    keeps = tuple(
        dict.fromkeys((_absolute(path), _resolved(path)) for path in protected)
    )
    seen: set[Path] = set()
    for raw_target in targets:
        target = _validate_target(raw_target)
        if target in seen or not raw_target.exists():
            continue
        seen.add(target)
        _purge_branch(raw_target, keeps)
    return [real for logical, real in keeps if logical.exists() or real.exists()]


def configured_project_paths(config_path: Path) -> list[Path]:
    """Read configured checkout paths; malformed config fails closed."""
    if not config_path.is_file():
        return []
    data = json.loads(config_path.read_text(encoding="utf-8"))
    paths: list[Path] = []
    for workspace in data.get("workspaces", []):
        if not isinstance(workspace, dict):
            continue
        for project in workspace.get("projects", []):
            if isinstance(project, dict) and project.get("path"):
                paths.append(Path(str(project["path"])))
    return paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", action="append", required=True, type=Path)
    parser.add_argument("--protect", action="append", default=[], type=Path)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    try:
        protected = list(args.protect)
        if args.config:
            protected.extend(configured_project_paths(args.config))
        kept = purge_targets(args.target, protected)
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    for path in kept:
        print(f"preserved project/install root: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
