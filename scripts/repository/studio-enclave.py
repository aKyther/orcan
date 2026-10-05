#!/usr/bin/env python3
"""Plan or create an empty Orcan configuration for Studio."""

from __future__ import annotations
import argparse, json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("plan", "apply"))
    parser.add_argument("--config", required=True)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    config = Path(args.config)
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
    if args.mode == "plan":
        print(json.dumps({"ok": True, "plan": plan}))
        return
    if not args.yes or not plan["ready"]:
        raise SystemExit("apply requires --yes and an absent configuration")
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps({"workspaces": []}, indent=2) + "\n")
    print(json.dumps({"ok": True, "result": {"config": str(config)}}))


if __name__ == "__main__":
    main()
