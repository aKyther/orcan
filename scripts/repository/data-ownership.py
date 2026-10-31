#!/usr/bin/env python3
"""Update data ownership without entering explicitly excluded directories."""

from __future__ import annotations

import argparse
import fnmatch
import os
from pathlib import Path


def update_ownership(
    root: str,
    uid: int,
    gid: int,
    exclusions: list[str],
    patterns: list[str] | None = None,
) -> bool:
    # Normalize lexically: resolving symlinks could contact an unresponsive mount.
    root = os.path.abspath(root)
    excluded = [os.path.abspath(path) for path in exclusions]

    def skip(path: str) -> bool:
        return any(
            os.path.commonpath([path, item]) == item for item in excluded
        ) or any(
            fnmatch.fnmatchcase(os.path.basename(path), pattern)
            for pattern in patterns or []
        )

    if skip(root):
        return True
    success = True

    def failed(_error: OSError) -> None:
        nonlocal success
        success = False

    def change(path: str) -> None:
        try:
            os.chown(path, uid, gid, follow_symlinks=False)
        except OSError as error:
            failed(error)

    change(root)
    pending = [] if os.path.islink(root) else [root]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    # Prune before even inspecting the excluded mount's type.
                    if skip(entry.path):
                        continue
                    change(entry.path)
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(entry.path)
        except OSError as error:
            failed(error)
    return success


def ownership_policy(config_path, exclusions, patterns, *, save=False):
    """Persist explicit opt-outs; every implicit sync reloads the same policy."""
    from config_io import dump_config, load_config_or_create

    if save and (exclusions or patterns) and not config_path.is_file():
        raise ValueError(
            "Persistent ownership exclusions require orcan.config.json; use orcan init PATH with the exclusion flags"
        )
    config = load_config_or_create(config_path)
    value = config.get("ownership", {})
    if not isinstance(value, dict) or set(value) - {"excluded_paths", "excluded_names"}:
        raise ValueError("ownership supports excluded_paths and excluded_names")
    paths = value.get("excluded_paths", [])
    names = value.get("excluded_names", [])
    if not isinstance(paths, list) or not isinstance(names, list):
        raise ValueError("ownership exclusions must be arrays")
    paths = paths + exclusions
    names = names + patterns
    if any(not isinstance(item, str) or not os.path.isabs(item) for item in paths):
        raise ValueError("ownership.excluded_paths requires absolute directory paths")
    if any(
        not isinstance(item, str) or not item or item.startswith("--") or "/" in item
        for item in names
    ):
        raise ValueError(
            "ownership.excluded_names requires directory names or globs without slashes"
        )
    paths = list(dict.fromkeys(os.path.abspath(item) for item in paths))
    names = list(dict.fromkeys(names))
    policy = dict(excluded_paths=paths, excluded_names=names)
    if save and (exclusions or patterns) and value != policy:
        config["ownership"] = policy
        dump_config(config_path, config)
    return paths, names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--save-policy", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--uid", type=int)
    parser.add_argument("--gid", type=int)
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--pattern", action="append", default=[])
    args = parser.parse_args()
    if args.save_policy and not args.config:
        parser.error("--save-policy requires --config")
    if args.config:
        try:
            args.exclude, args.pattern = ownership_policy(
                args.config, args.exclude, args.pattern, save=args.save_policy
            )
        except (ValueError, OSError) as error:
            parser.error(str(error))
    if args.check_only:
        return 0
    if args.root is None or args.uid is None or args.gid is None:
        parser.error("ownership updates require --root, --uid and --gid")
    return (
        0
        if update_ownership(args.root, args.uid, args.gid, args.exclude, args.pattern)
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
