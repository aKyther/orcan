"""Built-in capabilities and bounded, read-only runtime verification."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import stat
import subprocess
from pathlib import Path

IDS = {"ssh", "docker", "ttyd", "executor", "cockpit"}


def catalog(root: Path) -> list[dict]:
    result = []
    for name in sorted(IDS):
        value = json.loads((root / (name + ".json")).read_text())
        if value.get("id") != name or value.get("verifier") != name:
            raise ValueError("Invalid built-in plugin descriptor")
        result.append(value)
    return result


def listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def check(name: str) -> dict:
    if name == "redis":
        name = "executor"  # Compatibility alias for the original broker-based name.
    if name not in IDS:
        raise ValueError("Unknown plugin")
    enabled = ready = False
    detail = ""
    if name == "executor":
        enabled = os.environ.get("ORCAN_REDIS_ENABLED") == "1"
        if enabled:
            try:
                process = subprocess.run(
                    ["orcan-executor", "doctor"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                ready = process.returncode == 0
                detail = (
                    "broker and worker ready"
                    if ready
                    else "broker or worker unavailable"
                )
            except (OSError, subprocess.TimeoutExpired):
                detail = "executor unavailable"
    elif name == "docker":
        path = Path("/var/run/docker.sock")
        try:
            enabled = stat.S_ISSOCK(path.stat().st_mode)
        except OSError:
            pass
        ready = enabled and os.access(path, os.R_OK | os.W_OK)
        detail = (
            "socket accessible" if ready else "Docker socket absent or inaccessible"
        )
    elif name == "ssh":
        enabled = os.environ.get("ORCAN_SSH_ENABLED") == "1"
        home = Path.home() / ".ssh"
        agent = os.environ.get("SSH_AUTH_SOCK", "")
        ready = enabled and (home.is_dir() or bool(agent and Path(agent).exists()))
        detail = (
            "SSH mount/agent available; remote authentication not attempted"
            if ready
            else "SSH capability not enabled"
        )
    elif name == "ttyd":
        enabled = os.environ.get("ORCAN_SUPERVISOR_MODE") == "ttyd"
        ready = enabled and listening(int(os.environ.get("TTYD_PORT", "7681")))
        detail = (
            "auth enabled" if os.environ.get("TTYD_CREDENTIAL") else "auth disabled"
        )
    elif name == "cockpit":
        enabled = Path("/opt/orcan-cockpit/venv/bin/orcan-cockpit").is_file()
        ready = enabled and shutil.which("tmux") is not None
        detail = "UI available; direct access: orcan enter --shell or --tmux"
    result = {
        "plugin": name,
        "enabled": enabled,
        "ready": bool(ready),
        "detail": detail,
    }
    if name == "cockpit":
        result["resources"] = resources()
    return result


def resources(cgroup: Path = Path("/sys/fs/cgroup"), disk: Path | None = None) -> dict:
    result = {}
    try:
        current = int((cgroup / "memory.current").read_text()[:40])
        maximum = (cgroup / "memory.max").read_text()[:40].strip()
        result["memory_current_bytes"] = current
        if maximum != "max":
            limit = int(maximum)
            result["memory_limit_bytes"] = limit
            result["memory_percent"] = (
                round(100 * current / limit, 1) if limit else None
            )
        result["memory_events"] = {
            line.split()[0]: int(line.split()[1])
            for line in (cgroup / "memory.events").read_text()[:1000].splitlines()
            if len(line.split()) == 2
        }
    except (OSError, ValueError):
        pass
    try:
        usage = shutil.disk_usage(disk or Path.home())
        result["disk_free_bytes"] = usage.free
        result["disk_total_bytes"] = usage.total
    except OSError:
        pass
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["list", "doctor", "validate"], default="list", nargs="?"
    )
    parser.add_argument("--plugin", choices=sorted(IDS), action="append")
    args = parser.parse_args(argv)
    if args.command == "validate":
        root = Path(os.environ.get("ORCAN_ROOT", "."))
        entries = catalog(root / "plugins")
        commands = (root / "cli/commands/up.sh").read_text() + (
            root / "cli/commands/enter.sh"
        ).read_text()
        for entry in entries:
            for flag in entry["flags"]:
                if flag.split()[-1] not in commands:
                    raise ValueError("Plugin flag not handled by CLI: " + flag)
        print(json.dumps({"valid": True, "plugins": len(entries)}))
        return 0
    if args.command == "list":
        values = catalog(
            Path(os.environ.get("ORCAN_PLUGIN_CATALOG", "/opt/orcan/plugins"))
        )
    else:
        values = [check(name) for name in (args.plugin or sorted(IDS))]
    print(json.dumps(values))
    return int(
        args.command == "doctor"
        and any(v["enabled"] and not v["ready"] for v in values)
    )
