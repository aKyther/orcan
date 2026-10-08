#!/usr/bin/env python3
"""Plan or create an empty Orcan configuration for Studio."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

from path_guards import PathGuardError, checked_project_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("plan", "apply", "rollback"))
    parser.add_argument("--config", required=True)
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--ttyd-host-port", type=int)
    parser.add_argument("--cpus", type=float)
    parser.add_argument("--memory-gb", type=int)
    parser.add_argument("--image")
    parser.add_argument("--projects-root")
    args = parser.parse_args()
    config = Path(args.config)
    empty_config = {"workspaces": []}
    if args.image is not None:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._/:@-]*", args.image):
            parser.error("invalid Docker image reference")
        empty_config["image"] = args.image
    if args.projects_root is not None:
        root = Path(args.projects_root)
        if (
            not root.is_absolute()
            or "\n" in args.projects_root
            or "\r" in args.projects_root
            or "$" in args.projects_root
            or "`" in args.projects_root
            or (root.exists() and not root.is_dir())
        ):
            parser.error(
                "project root must be an absolute directory without line breaks"
            )
        try:
            empty_config["projects_root"] = str(
                checked_project_dir(root, must_exist=False)
            )
        except PathGuardError as error:
            parser.error(str(error))
    if args.ttyd_host_port is not None:
        if not 1024 <= args.ttyd_host_port <= 65535:
            parser.error("browser-terminal host port must be 1024–65535")
        empty_config["ttyd"] = {"host_port": args.ttyd_host_port}
    resources = {}
    if args.cpus is not None:
        if not math.isfinite(args.cpus) or not 0 < args.cpus <= 1024:
            parser.error("CPU limit must be greater than zero and at most 1024")
        resources["cpus"] = args.cpus
    if args.memory_gb is not None:
        if not 1 <= args.memory_gb <= 65536:
            parser.error("RAM must be 1–65536 GiB")
        resources["memory"] = f"{args.memory_gb}g"
    if resources:
        empty_config["resources"] = resources
    plan = {
        "operation": "empty_enclave",
        "config": str(config),
        "changes": [
            f"create empty configuration {config}",
            "run orcan sync",
            "run orcan up with selected runtime options",
        ],
        "ready": not config.exists(),
    }
    if resources:
        plan["changes"].append(f"container resources: {json.dumps(resources)}")
    if args.image:
        plan["changes"].append(f"use local image {args.image} (no download)")
    if args.projects_root:
        plan["changes"].append(f"share project root {args.projects_root}")
    if args.ttyd_host_port is not None:
        plan["changes"].append(
            f"publish browser terminal on host port {args.ttyd_host_port}"
        )
    if args.mode == "plan":
        print(json.dumps({"ok": True, "plan": plan}))
        return
    if args.mode == "rollback":
        if not args.yes:
            raise SystemExit("rollback requires --yes")
        if (
            not config.is_file()
            or json.loads(config.read_text(encoding="utf-8")) != empty_config
        ):
            raise SystemExit(
                "refusing to remove a configuration that is not the empty Studio configuration"
            )
        config.unlink()
        print(json.dumps({"ok": True, "result": {"rolled_back": str(config)}}))
        return
    if not args.yes or not plan["ready"]:
        raise SystemExit("apply requires --yes and an absent configuration")
    config.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation closes the race between two Studio apply requests.
    with config.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(empty_config, indent=2) + "\n")
    print(json.dumps({"ok": True, "result": {"config": str(config)}}))


if __name__ == "__main__":
    main()
