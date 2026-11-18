#!/usr/bin/env python3
"""Preview/clean the checkout's generated Studio Cargo target, never external caches."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


def allocated(root: Path) -> tuple[int, bool]:
    total = 0
    count = 0
    pending = [root]
    seen = set()
    while pending:
        path = pending.pop()
        try:
            stat = path.lstat()
            count += 1
            if count > 100000:
                return total, True
            if path.is_symlink():
                continue
            identity = (stat.st_dev, stat.st_ino)
            if identity in seen:
                continue
            seen.add(identity)
            if path.is_dir():
                with os.scandir(path) as entries:
                    for entry in entries:
                        if count + len(pending) >= 100000:
                            return total, True
                        pending.append(Path(entry.path))
            else:
                total += stat.st_blocks * 512
        except FileNotFoundError:
            continue
    return total, False


def maintain(
    root: Path, *, apply: bool = False, automatic: bool = False, budget_mb: int = 2048
) -> dict:
    root = root.resolve()
    studio = root / "studio"
    target = studio / "target"
    manifest = studio / "Cargo.toml"
    if studio.is_symlink() or target.is_symlink() or not manifest.is_file():
        raise ValueError(
            "Expected a local Studio workspace and a non-symlink studio/target."
        )
    if not 1 <= budget_mb <= 1048576:
        raise ValueError("Studio build budget must be 1..1048576 MiB.")
    size, incomplete = allocated(target)
    report = {
        "path": str(target),
        "allocated_bytes": size,
        "incomplete": incomplete,
        "budget_bytes": budget_mb * 1024**2,
        "removed": False,
        "automatic": automatic,
    }
    external = os.environ.get("CARGO_TARGET_DIR")
    if external and Path(external).expanduser().resolve() != target:
        report["preserved"] = (
            "External CARGO_TARGET_DIR; its lifecycle belongs to the caller."
        )
        return report
    if apply or (automatic and (size > report["budget_bytes"] or incomplete)):
        tracked = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--", "studio/target"],
            capture_output=True,
            text=True,
            check=True,
        )
        if tracked.stdout.strip():
            raise ValueError("Refusing to clean a target directory with tracked files.")
        # Cargo owns build locking. Do not bypass it with recursive filesystem removal.
        subprocess.run(
            [
                "cargo",
                "clean",
                "--manifest-path",
                str(manifest),
                "--target-dir",
                str(target),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        report["removed"] = True
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument(
        "--auto",
        action="store_true",
        help="Clean before building only when over budget.",
    )
    parser.add_argument("--budget-mb", type=int, default=2048)
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                maintain(
                    args.root,
                    apply=args.apply,
                    automatic=args.auto,
                    budget_mb=args.budget_mb,
                )
            )
        )
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({"error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
