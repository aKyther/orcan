#!/usr/bin/env python3
"""Load / dump / discover orcan user config (JSON only — Python stdlib)."""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, NoReturn

JSON_NAME = "orcan.config.json"


def die(msg: str) -> NoReturn:
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
                f"then run orcan sync"
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


def dump_config(
    path: Path, data: dict[str, Any], *, expected: bytes | None = None
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not is_json_path(path):
        die(f"unsupported config extension for write (use .json): {path}")
    pending = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as stream:
            pending = Path(stream.name)
            if path.exists():
                os.chmod(pending, stat.S_IMODE(path.stat().st_mode))
            stream.write(json.dumps(data, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        if expected is not None and path.read_bytes() != expected:
            raise ValueError("configuration changed; reload before applying")
        os.replace(pending, path)
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


def default_write_path(root: Path) -> Path:
    return root / JSON_NAME


def find_workspace(cfg: dict[str, Any], name: str) -> dict[str, Any] | None:
    """First workspaces[] entry whose name matches, or None."""
    for ws in cfg.get("workspaces") or []:
        if isinstance(ws, dict) and ws.get("name") == name:
            return ws
    return None
