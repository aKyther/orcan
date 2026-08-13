#!/usr/bin/env python3
"""Format cached Claude/Cursor usage for tmux status-right (no network)."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def colour_for(*values) -> str:
    worst = 0
    for value in values:
        if isinstance(value, int):
            worst = max(worst, value)
    if worst >= 90:
        return "#f87171"
    if worst >= 70:
        return "#fbbf24"
    return "#67e8f9"


def main() -> int:
    cache_dir = Path(
        os.environ.get("ORCAN_AI_USAGE_DIR")
        or (Path(os.environ.get("HOME", "/home/developer")) / ".cache" / "orcan")
    )
    try:
        max_age = int(os.environ.get("ORCAN_AI_USAGE_MAX_AGE", "1800"))
    except ValueError:
        max_age = 1800

    now = int(time.time())
    paths = sorted(cache_dir.glob("ai-usage-*.json"))
    if not paths:
        legacy = cache_dir / "ai-usage.json"
        if legacy.is_file():
            paths = [legacy]

    segments = []
    seen: set[str] = set()
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        try:
            updated_i = int(data.get("updated_at"))
        except (TypeError, ValueError):
            continue
        if now - updated_i > max_age:
            continue

        provider = str(data.get("provider") or "ai").strip() or "ai"
        if provider in seen:
            continue
        seen.add(provider)

        parts = []
        ctx = data.get("context_pct")
        five = data.get("five_hour_pct")
        seven = data.get("seven_day_pct")
        cost = data.get("cost_usd")
        if isinstance(ctx, int):
            parts.append(f"◌ {ctx}%")
        if isinstance(five, int):
            parts.append(f"◷ {five}%")
        if isinstance(seven, int):
            parts.append(f"◫ {seven}%")
        if isinstance(cost, (int, float)) and float(cost) > 0:
            parts.append(f"${float(cost):.2f}")
        if not parts:
            continue

        colour = colour_for(
            ctx if isinstance(ctx, int) else 0,
            five if isinstance(five, int) else 0,
            seven if isinstance(seven, int) else 0,
        )
        # ✦ = AI usage; short provider name; metric icons with a light gap before values
        segments.append(f"#[fg={colour}]✦ {provider} " + " ".join(parts))

    sys.stdout.write("#[fg=#334155] · #[default]".join(segments))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
