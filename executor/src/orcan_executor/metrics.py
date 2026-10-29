"""Exact local byte/line accounting; token counts are explicitly estimates."""

import json
from pathlib import Path


def wire(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def log_size(path: Path) -> tuple[int, int]:
    total = lines = 0
    last = b""
    if path.is_file():
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                total += len(chunk)
                lines += chunk.count(b"\n")
                last = chunk[-1:]
    return total, lines + int(bool(total) and last != b"\n")


def model_result(payload: dict) -> dict:
    """Keep dashboard instrumentation out of model-facing completion messages."""
    result = payload.copy()
    if isinstance(result.get("summary"), dict):
        result["summary"] = result["summary"].copy()
        result["summary"].pop("metrics", None)
    return result


def measure_result(payload: dict) -> None:
    """Count canonical model completion JSONL, excluding the Redis cursor.

    The stream and durable summary retain instrumentation for the dashboard;
    listeners remove it before emitting a result to the agent.
    """
    metrics = payload.get("summary", {}).get("metrics")
    if metrics is None:
        return
    size = len(wire(model_result(payload)).encode("utf-8")) + 1
    metrics["result_bytes"] = size
    metrics["result_lines"] = 1
    difference = metrics["log_bytes"] - size
    metrics["reduction_bytes"] = difference
    metrics["reduction_percent"] = (
        round(100 * difference / metrics["log_bytes"], 2) if metrics["log_bytes"] else None
    )
    metrics["estimated_tokens_avoided"] = max(0, difference // 4)
