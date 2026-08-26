"""Last reflection/recap batch feedback for the ASSERTIONS card.

Stdlib-only — reads ``.orcan/recap/*.json`` + ``reflection-state.json`` and
optional automation model_check so the human sees whether the ~20-turn loop
is alive, not only its pending side-effects.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

for _lib in (
    Path("/usr/local/lib"),
    Path(__file__).resolve().parents[3] / "docker" / "rootfs" / "usr" / "local" / "lib",
):
    if (_lib / "orcan" / "context_inbox.py").is_file():
        sys.path.insert(0, str(_lib))
        break

from orcan.context_inbox import format_pending_age  # noqa: E402


def _parse_iso_mtime(value: str) -> float | None:
    raw = (value or "").strip()
    if not raw:
        return None
    # datetime.fromisoformat handles ``2026-01-01T00:00:00+00:00``; Z → +00:00.
    try:
        from datetime import datetime

        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _bullet_count(rolling_compact: str) -> int:
    lines = [ln.strip() for ln in (rolling_compact or "").splitlines() if ln.strip()]
    if not lines:
        return 0
    # Prefer markdown bullets; otherwise each non-empty line is one fact.
    bullets = [ln for ln in lines if ln.startswith(("-", "*", "•"))]
    return len(bullets) if bullets else len(lines)


def _newest_recap(workspace_root: Path) -> dict[str, Any] | None:
    recap_dir = workspace_root / ".orcan" / "recap"
    if not recap_dir.is_dir():
        return None
    best: tuple[float, dict[str, Any]] | None = None
    for path in recap_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        ts = _parse_iso_mtime(str(data.get("updated_at") or ""))
        if ts is None:
            try:
                ts = path.stat().st_mtime
            except OSError:
                continue
        if best is None or ts > best[0]:
            best = (ts, data)
    return None if best is None else best[1]


def _latest_error(workspace_root: Path) -> tuple[str, float | None]:
    state_path = workspace_root / ".orcan" / "reflection-state.json"
    if not state_path.is_file():
        return "", None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "", None
    if not isinstance(state, dict):
        return "", None
    newest_msg = ""
    newest_ts: float | None = None
    for entry in state.values():
        if not isinstance(entry, dict):
            continue
        msg = str(entry.get("last_recap_error") or entry.get("last_error") or "").strip()
        if not msg:
            continue
        ts = _parse_iso_mtime(
            str(entry.get("last_recap_error_at") or entry.get("last_error_at") or "")
        )
        if newest_ts is None or (ts is not None and ts >= (newest_ts or 0)):
            newest_msg = msg
            newest_ts = ts
    return newest_msg, newest_ts


def _model_status() -> str:
    try:
        from orcan.automation import model_check_result

        mc = model_check_result()
    except Exception:
        return "haiku ?"
    if not isinstance(mc, dict):
        return "haiku ?"
    model = str(mc.get("model") or "haiku")
    if mc.get("ok") is True:
        return f"{model} ok"
    if mc.get("ok") is False:
        return f"{model} fail"
    return f"{model} ?"


def last_batch_feedback(workspace_root: Path, *, now: float | None = None) -> str:
    """One line: ``last batch: 4 facts · 2h · haiku ok`` or fail variant."""
    clock = time.time() if now is None else now
    err, err_ts = _latest_error(workspace_root)
    recap = _newest_recap(workspace_root)
    model = _model_status()

    if err:
        age = format_pending_age(err_ts, now=clock) if err_ts else ""
        age_bit = f" · {age}" if age else ""
        short = err.replace("\n", " ")[:40]
        return f"last batch: fail ({short}){age_bit} · {model}"

    if not recap:
        return f"last batch: (none yet) · {model}"

    facts = _bullet_count(str(recap.get("rolling_compact") or ""))
    batches = int(recap.get("batch_count") or 0)
    updated = _parse_iso_mtime(str(recap.get("updated_at") or ""))
    age = format_pending_age(updated, now=clock) if updated else ""
    mid = f"{facts} facts" if facts else (f"{batches} batches" if batches else "empty")
    age_bit = f" · {age}" if age else ""
    return f"last batch: {mid}{age_bit} · {model}"
