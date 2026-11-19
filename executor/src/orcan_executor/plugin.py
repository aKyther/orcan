"""The bundled Redis plugin owns executor defaults, ranges and variable names."""

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def fields() -> dict:
    source = Path(__file__).resolve().parents[3] / "plugins/redis/plugin.json"
    if not source.is_file():
        source = Path(__file__).with_name("redis-plugin.json")
    if not source.is_file():
        source = Path("/opt/orcan/plugins/redis/plugin.json")
    # Wheels carry the same descriptor; no user settings path can replace it.
    value = json.loads(source.read_text())
    if value.get("id") != "redis" or value.get("version") != 1:
        raise ValueError("Invalid bundled Redis plugin metadata")
    return value["fields"]
