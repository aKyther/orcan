"""Optional host-mounted artifact storage; metadata and locks stay local."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

DEFAULTS = {"path": "", "mount_path": "", "require_mount": True}


def resolve(value=None):
    value = {} if value is None else value
    if not isinstance(value, dict) or set(value) - DEFAULTS.keys():
        raise ValueError("storage supports path, mount_path and require_mount")
    result = DEFAULTS | value
    raw = result["path"]
    if not isinstance(raw, str) or type(result["require_mount"]) is not bool:
        raise ValueError(
            "storage.path must be text; storage.require_mount must be boolean"
        )
    if raw:
        if not Path(raw).is_absolute() or any(c in raw for c in "\x00\n\r$`"):
            raise ValueError(
                "storage.path must be an absolute host path without shell expansions"
            )
        path = Path(os.path.normpath(raw))
        if path in map(Path, ["/", "/proc", "/sys", "/dev", "/run", "/tmp"]) or any(
            base in path.parents for base in map(Path, ["/proc", "/sys", "/dev"])
        ):
            raise ValueError(
                "Choose a dedicated storage directory, not a system root or virtual filesystem"
            )
        result["path"] = str(path)
    mount = result["mount_path"]
    if not isinstance(mount, str) or (
        mount
        and (not Path(mount).is_absolute() or any(c in mount for c in "\x00\n\r$`"))
    ):
        raise ValueError("storage.mount_path must be an absolute mountpoint or empty")
    if mount:
        result["mount_path"] = os.path.normpath(mount)
        if raw and not Path(result["path"]).is_relative_to(result["mount_path"]):
            raise ValueError("storage.path must be inside storage.mount_path")
    return result


def check(path, require_mount=True, mount_path=""):
    root = Path(path)
    if not root.is_dir():
        raise ValueError(
            f"Artifact storage is unavailable: {root}. Mount it before orcan up."
        )
    if root.resolve() != root:
        raise ValueError(
            "Use the canonical host storage path, without symlink components"
        )
    anchor = Path(mount_path) if mount_path else root
    if not root.is_relative_to(anchor):
        raise ValueError("Artifact storage is outside the configured mountpoint")
    if require_mount and not anchor.is_mount():
        raise ValueError(
            f"Artifact storage is not mounted: {root}. No local fallback directory will be created."
        )
    if not os.access(root, os.R_OK | os.W_OK | os.X_OK):
        raise ValueError(f"Artifact storage is not accessible for this user: {root}")
    return root


def prepare(path, require_mount=True, instance="default", mount_path=""):
    root = check(path, require_mount, mount_path)
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", instance):
        raise ValueError("Invalid storage instance namespace")
    current = root
    for part in ("orcan", instance, "scratch"):
        current = current / part
        if current.is_symlink():
            raise ValueError("Storage namespace must not contain symlinks")
        current.mkdir(exist_ok=True)
    return current


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    path = os.environ.get("ORCAN_STORAGE_ROOT", "")
    if not path:
        return 0
    try:
        require = os.environ.get("ORCAN_STORAGE_REQUIRE_MOUNT", "1") == "1"
        root = (
            prepare(
                path,
                require,
                os.environ.get("ORCAN_NAMED_INSTANCE") or "default",
                os.environ.get("ORCAN_STORAGE_MOUNT", ""),
            )
            if args.prepare
            else check(path, require, os.environ.get("ORCAN_STORAGE_MOUNT", ""))
        )
        print(json.dumps({"storage": str(root), "ready": True}))
        return 0
    except (OSError, ValueError) as error:
        print(f"Artifact storage: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
