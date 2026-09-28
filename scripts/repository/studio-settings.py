#!/usr/bin/env python3
"""Read-only settings snapshot and plan endpoint for Orcan Studio."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan",))
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    path = Path(args.config).resolve()
    if not path.is_file():
        print(json.dumps({"ok": False, "error": "Orcan configuration does not exist"}))
        raise SystemExit(2)
    data = json.loads(path.read_text(encoding="utf-8"))
    workspaces = data.get("workspaces") or []
    print(
        json.dumps(
            {
                "ok": True,
                "plan": {
                    "operation": "settings_snapshot",
                    "config": str(path),
                    "workspaces": workspaces,
                    "changes": [],
                    "blockers": [],
                    "ready": True,
                },
            },
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
