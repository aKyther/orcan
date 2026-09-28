#!/usr/bin/env python3
"""Emit a read-only, versioned Orcan Sandbox report for Orcan Studio."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path


def docker_probe(docker: str, image: str, container: str) -> dict[str, object]:
    """Return Docker facts without changing images, containers, or configuration."""
    if not shutil.which(docker):
        return {
            "available": False,
            "image": {"name": image, "present": False},
            "container": {"name": container, "state": "unavailable"},
        }

    try:
        daemon = (
            subprocess.run(
                [docker, "info"], capture_output=True, text=True, timeout=5, check=False
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        daemon = False
    if not daemon:
        return {
            "available": False,
            "image": {"name": image, "present": False},
            "container": {"name": container, "state": "unavailable"},
        }

    image_present = (
        subprocess.run(
            [docker, "image", "inspect", image],
            capture_output=True,
            text=True,
            check=False,
        ).returncode
        == 0
    )
    state = subprocess.run(
        [docker, "inspect", "--format", "{{.State.Status}}", container],
        capture_output=True,
        text=True,
        check=False,
    )
    container_state = state.stdout.strip() if state.returncode == 0 else "missing"
    return {
        "available": True,
        "image": {"name": image, "present": image_present},
        "container": {"name": container, "state": container_state},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=int, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--home", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--projects-root", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--container", required=True)
    args = parser.parse_args()

    docker = docker_probe(
        os.environ.get("ORCAN_STUDIO_DOCKER", "docker"), args.image, args.container
    )
    report = {
        "protocol": {
            "name": "orcan-studio",
            "version": args.protocol,
            "methods": ["probe"],
        },
        "sandbox": {"version": args.version},
        "host": {
            "os": platform.system().lower(),
            "architecture": platform.machine().lower(),
        },
        "paths": {
            "home": str(Path(args.home)),
            "data": str(Path(args.data)),
            "projects_root": str(Path(args.projects_root)),
        },
        "capabilities": {
            "docker": bool(docker["available"]),
            "git": shutil.which("git") is not None,
            "managed_projects": True,
            "live_reconcile": True,
        },
        "runtime": {
            "config": "present" if Path(args.config).is_file() else "missing",
            "generated": "present" if Path(args.runtime).is_file() else "missing",
            "docker": docker,
        },
    }
    print(json.dumps(report, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
