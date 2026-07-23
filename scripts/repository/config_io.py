#!/usr/bin/env python3
"""Load / dump / discover cind user config (YAML preferred, JSON still accepted)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

YAML_NAMES = ("cind.config.yaml", "cind.config.yml")
JSON_NAME = "cind.config.json"
ALL_NAMES = YAML_NAMES + (JSON_NAME,)


def die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def require_yaml() -> None:
    if yaml is None:
        die(
            "PyYAML is required to read/write cind.config.yaml "
            "(install: sudo apt install python3-yaml  or  pip install pyyaml)"
        )


def is_yaml_path(path: Path) -> bool:
    return path.suffix.lower() in {".yaml", ".yml"}


def is_json_path(path: Path) -> bool:
    return path.suffix.lower() == ".json"


def discover_config(root: Path) -> Path | None:
    """Prefer YAML over JSON when several exist."""
    for name in ALL_NAMES:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def load_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if is_yaml_path(path):
        require_yaml()
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            die(f"invalid YAML in {path}: {exc}")
    elif is_json_path(path):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            die(f"invalid JSON in {path}: {exc}")
    else:
        die(f"unsupported config extension (use .yaml / .yml / .json): {path}")
    if data is None:
        data = {}
    if not isinstance(data, dict):
        die(f"config root must be a mapping/object: {path}")
    return data


def dump_config(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if is_yaml_path(path):
        require_yaml()
        text = yaml.safe_dump(
            data,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
        if not text.endswith("\n"):
            text += "\n"
        path.write_text(text, encoding="utf-8")
        return
    if is_json_path(path):
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return
    die(f"unsupported config extension for write: {path}")


def default_write_path(root: Path) -> Path:
    """Path used when creating a new config (YAML)."""
    return root / "cind.config.yaml"
