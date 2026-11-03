#!/usr/bin/env python3
"""Export validated JSON settings to a host shell; no dotenv or shell input."""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
from pathlib import Path

from config_io import load_config
from host_config import host_environment

STATE_KEYS = {
    "WITH_DOCKER", "WITH_GIT", "WITH_NETWORK", "WITH_TTYD", "WITH_TTYD_AUTH",
    "NETWORK_NAME", "WITH_GITHUB", "GITHUB_HOSTNAME", "WITH_GITLAB",
    "GITLAB_HOSTNAME", "WITH_REDIS",
}


def shell_exports(values: dict) -> str:
    return "\n".join(f"export {key}={shlex.quote(str(value))}" for key, value in values.items())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", default=os.environ.get("ORCAN_HOME", "."))
    parser.add_argument("--config", default=os.environ.get("CONFIG") or os.environ.get("ORCAN_CONFIG_FILE", ""))
    parser.add_argument("--state-read", type=Path)
    parser.add_argument("--state-write", type=Path)
    parser.add_argument("values", nargs="*")
    args = parser.parse_args()
    if args.state_read:
        values = json.loads(args.state_read.read_text())
        if not isinstance(values, dict) or set(values) - STATE_KEYS or any(
            not isinstance(value, (str, int)) or "\x00" in str(value)
            for value in values.values()
        ):
            raise ValueError("invalid launch state")
        print(shell_exports(values))
        return
    if args.state_write:
        values = dict(item.split("=", 1) for item in args.values)
        if set(values) - STATE_KEYS:
            raise ValueError("unknown launch state field")
        args.state_write.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.state_write.with_suffix(".tmp")
        temporary.write_text(json.dumps(values, indent=2) + "\n")
        temporary.replace(args.state_write)
        return
    home = Path(args.home).resolve()
    config = Path(args.config) if args.config else home / "orcan.config.json"
    cfg = load_config(config) if config.exists() else {}
    runtime_path = Path(os.environ.get("ORCAN_RUNTIME_DIR") or home / "mounts") / "runtime-config.json"
    runtime = json.loads(runtime_path.read_text()) if runtime_path.exists() else {}
    values = host_environment(cfg, home, runtime)
    for field, variable in (("name", "GIT_AUTHOR_NAME"), ("email", "GIT_AUTHOR_EMAIL")):
        result = subprocess.run(["git", "config", "--global", "--get", "user." + field], capture_output=True, text=True, check=False)
        values[variable] = result.stdout.strip() if result.returncode == 0 else ""
    print(shell_exports(values))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TypeError) as error:
        raise SystemExit("orcan: invalid JSON runtime settings: " + str(error)) from None
