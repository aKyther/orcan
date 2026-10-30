#!/usr/bin/env python3
"""Update data ownership without entering explicitly excluded directories."""

from __future__ import annotations

import argparse
import fnmatch
import os


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--uid", type=int, required=True)
    parser.add_argument("--gid", type=int, required=True)
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--pattern", action="append", default=[])
    args = parser.parse_args()
    return (
        0
        if update_ownership(args.root, args.uid, args.gid, args.exclude, args.pattern)
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
