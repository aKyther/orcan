#!/usr/bin/env python3
"""Load / dump / discover orcan user config (JSON only — Python stdlib)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

JSON_NAME = "orcan.config.json"


def die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def is_json_path(path: Path) -> bool:
    return path.suffix.lower() == ".json"


def discover_config(root: Path) -> Path | None:
    """Return orcan.config.json if present."""
    json_path = root / JSON_NAME
    if json_path.is_file():
        return json_path
    # Leftover YAML from older setups — point users at JSON.
    for name in ("orcan.config.yaml", "orcan.config.yml"):
        if (root / name).is_file():
            die(
                f"found {name}; host config is JSON-only. "
                f"Convert to {JSON_NAME} (e.g. yq -o=json {name} > {JSON_NAME}), "
                "then run make env"
            )
    return None


def load_config(path: Path) -> dict[str, Any]:
    if path.suffix.lower() in {".yaml", ".yml"}:
        die(f"YAML config is not supported ({path.name}). Use {JSON_NAME}.")
    if not is_json_path(path):
        die(f"unsupported config extension (use .json): {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(f"invalid JSON in {path}: {exc}")
    if data is None:
        data = {}
    if not isinstance(data, dict):
        die(f"config root must be an object: {path}")
    return data


def dump_config(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not is_json_path(path):
        die(f"unsupported config extension for write (use .json): {path}")
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def default_write_path(root: Path) -> Path:
    return root / JSON_NAME
