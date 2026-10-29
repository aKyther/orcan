#!/usr/bin/env python3
"""Resolve an explicit image build profile without Docker or shell evaluation."""

import argparse
import json
import sys
from pathlib import Path

AGENTS = {"cursor", "claude", "codex", "gemini", "copilot"}


def resolve(config: dict, override: str = "") -> dict:
    if not isinstance(config, dict):
        raise TypeError("configuration must be an object")
    profile = config.get("build", {})
    if not isinstance(profile, dict) or set(profile) - {"agents", "tools"}:
        raise ValueError("build supports only agents and tools")
    agents = override.split("+") if override else profile.get("agents", [])
    if not isinstance(agents, list) or any(
        not isinstance(name, str) or name not in AGENTS for name in agents
    ):
        raise ValueError("build.agents must list known Orcan agents")
    if not agents:
        raise ValueError(
            "choose at least one agent: orcan build --agent codex, --all-agents, or build.agents in orcan.config.json"
        )
    tools = profile.get("tools", {})
    if (
        not isinstance(tools, dict)
        or set(tools) - {"go", "rust"}
        or any(type(value) is not bool for value in tools.values())
    ):
        raise ValueError("build.tools supports boolean go and rust options")
    return {
        "agents": list(dict.fromkeys(agents)),
        "tools": {"go": tools.get("go", True), "rust": tools.get("rust", True)},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="")
    parser.add_argument("--agents", default="")
    args = parser.parse_args()
    try:
        config = json.loads(Path(args.config).read_text()) if args.config else {}
        print(json.dumps(resolve(config, args.agents)))
    except (ValueError, OSError, TypeError) as error:
        print("Invalid image profile: " + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
