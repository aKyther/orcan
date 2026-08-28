#!/usr/bin/env python3
"""Reconcile workspace meta on the host ($ORCAN_HOME/workspaces/).

Container reconcile uses ``projects[].root`` = ``/home/developer/workspaces/<name>``,
which only exists inside the container. Host meta lives at ``meta_path`` from
runtime-config.json — the same tree bind-mounted as ``/home/developer/workspaces/``.

Called from ``orcan sync`` so symlink fixes apply even when the container is
down; a later live ``orcan-runtime-reconcile`` is idempotent.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "docker" / "rootfs" / "usr" / "local" / "lib"))

from orcan.reconcile import apply_workspaces  # noqa: E402


def die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def runtime_path(home: Path) -> Path:
    env = os.environ.get("ORCAN_CONFIG_HOST", "").strip()
    if env:
        return Path(env)
    return home / "mounts" / "runtime-config.json"


def host_cfg_from_runtime(runtime: dict) -> dict:
    """Map container workspace roots to host ``meta_path`` trees."""
    workspaces: list[dict] = []
    for ws in runtime.get("workspaces") or []:
        if not isinstance(ws, dict) or ws.get("enabled") is False:
            continue
        meta_raw = str(ws.get("meta_path") or "").strip()
        if not meta_raw:
            continue
        meta = Path(meta_raw)
        mapped = deepcopy(ws)
        mapped["root"] = str(meta)
        projects: list[dict] = []
        for item in mapped.get("projects") or []:
            if not isinstance(item, dict):
                continue
            proj = deepcopy(item)
            pname = str(proj.get("name") or "").strip()
            if pname:
                proj["workspace_path"] = str(meta / pname)
            projects.append(proj)
        mapped["projects"] = projects
        workspaces.append(mapped)
    return {"workspaces": workspaces}


def defaults_root(orcan_root: Path) -> Path:
    return orcan_root / "docker" / "rootfs" / "opt" / "cursor-defaults" / "templates" / "workspace"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--home",
        default=os.environ.get("ORCAN_HOME", "").strip(),
        help="ORCAN_HOME (default: $ORCAN_HOME)",
    )
    parser.add_argument(
        "--root",
        default=os.environ.get("ORCAN_ROOT", "").strip(),
        help="ORCAN install root for templates (default: $ORCAN_ROOT)",
    )
    args = parser.parse_args()

    if not args.home:
        die("ORCAN_HOME is not set")
    if not args.root:
        die("ORCAN_ROOT is not set")

    home = Path(args.home).resolve()
    orcan_root = Path(args.root).resolve()
    cfg_path = runtime_path(home)
    if not cfg_path.is_file():
        die(f"runtime config not found: {cfg_path} (run: orcan sync after orcan init)")

    runtime = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg = host_cfg_from_runtime(runtime)
    if not cfg["workspaces"]:
        print("host reconcile: no enabled workspaces in runtime config")
        return 0

    templates = defaults_root(orcan_root)
    if not templates.is_dir():
        die(f"workspace templates missing under ORCAN_ROOT: {templates}")

    report = apply_workspaces(
        cfg,
        templates,
        home / "workspaces",
    )
    for ws in report.workspaces:
        print(f"workspace ready: {ws.root} ({ws.repo_count} repo(s), tmux={ws.name})")
        for created in ws.symlinks_created:
            print(f"  + symlink: {created}")
        for removed in ws.symlinks_removed:
            print(f"  - symlink: {removed}")
        for relocated in ws.dirs_relocated:
            print(f"  ~ relocated: {relocated}")
        for missing in ws.skipped_missing_repos:
            print(f"  ! skip missing repo mount: {missing}")
    print(
        f"host workspaces reconciled: {len(report.workspaces)} "
        f"({report.total_repos()} repo(s), changed={report.changed()})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
