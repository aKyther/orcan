"""Background Context automation control (scan / reflect / host sync).

Shared flag on the history bind so both the in-container
``orcan-context-scan`` (supervisord) and the host ``context_syncd`` see the
same switches. Cockpit toggles them; workers idle when disabled or paused.

  ~/.local/share/orcan/history/supervisor/automation.json
  host: $ORCAN_DATA/history/supervisor/automation.json

Fields:

  ``enabled`` — master switch (false = feature off; default true).
  ``paused``  — temporary idle while enabled (cockpit ``[p]``).
  ``model_check`` — cached result from ``context_model_check.check_recap_model``.

Human accept/reject of assertions stays required — these only stop the
automatic *when-to-run* machinery, not the review gate.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from orcan.context_model_check import check_recap_model

AUTOMATION_FILENAME = "automation.json"
DEFAULT_MODEL = "haiku"
MODEL_CHECK_MAX_AGE_SECONDS = 900
# Set when we auto-disable because Claude Code is missing; cleared when
# claude returns so we can turn automation back on without fighting a
# deliberate human "off".
AUTO_DISABLED_NO_CLAUDE = "auto_disabled_no_claude"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def automation_dir() -> Path:
    """Durable dir shared host ↔ container via the history bind."""
    data = (os.environ.get("ORCAN_DATA") or "").strip()
    if data:
        return Path(data) / "history" / "supervisor"
    return Path.home() / ".local" / "share" / "orcan" / "history" / "supervisor"


def automation_path() -> Path:
    return automation_dir() / AUTOMATION_FILENAME


def load_automation() -> dict[str, Any]:
    path = automation_path()
    if not path.is_file():
        return {"enabled": True, "paused": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"enabled": True, "paused": False}
    if not isinstance(data, dict):
        return {"enabled": True, "paused": False}
    if "enabled" not in data:
        data["enabled"] = True
    return data


def save_automation(state: dict[str, Any]) -> dict[str, Any]:
    path = automation_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state


def is_enabled() -> bool:
    return bool(load_automation().get("enabled", True))


def is_paused() -> bool:
    return bool(load_automation().get("paused"))


def is_active() -> bool:
    """True when background scan/sync may run (enabled, not paused, claude OK)."""
    state = load_automation()
    if not state.get("enabled", True):
        return False
    if bool(state.get("paused")):
        return False
    # Soft gate: if we already know the model is missing, do not claim active.
    if not claude_on_path():
        return False
    mc = state.get("model_check")
    if isinstance(mc, dict) and mc.get("ok") is False:
        return False
    return True


def claude_on_path() -> bool:
    return shutil.which("claude") is not None


def sync_automation_to_claude_availability() -> dict[str, Any]:
    """Disable assertions automation when ``claude`` is missing; restore if we
    were the ones who turned it off.

    Manual Review of inbox/queue still works — only background propose/recap
    needs Claude Code. Returns the (possibly updated) automation state.
    """
    state = load_automation()
    if not claude_on_path():
        if state.get("enabled", True) or not state.get(AUTO_DISABLED_NO_CLAUDE):
            state["enabled"] = False
            state["paused"] = False
            state[AUTO_DISABLED_NO_CLAUDE] = True
            state["updated_at"] = _now_iso()
            return save_automation(state)
        return state
    # Claude is back — only re-enable if *we* auto-disabled earlier.
    if state.get(AUTO_DISABLED_NO_CLAUDE):
        state["enabled"] = True
        state["paused"] = False
        state.pop(AUTO_DISABLED_NO_CLAUDE, None)
        state["updated_at"] = _now_iso()
        return save_automation(state)
    return state


def set_paused(paused: bool) -> dict[str, Any]:
    state = load_automation()
    state["paused"] = bool(paused)
    state["updated_at"] = _now_iso()
    return save_automation(state)


def set_enabled(enabled: bool) -> dict[str, Any]:
    state = load_automation()
    state["enabled"] = bool(enabled)
    if not enabled:
        state["paused"] = False
    # Human toggle overrides auto-disable bookkeeping.
    state.pop(AUTO_DISABLED_NO_CLAUDE, None)
    state["updated_at"] = _now_iso()
    return save_automation(state)


def toggle_paused() -> dict[str, Any]:
    if not is_enabled():
        return load_automation()
    return set_paused(not is_paused())


def toggle_enabled() -> dict[str, Any]:
    return set_enabled(not is_enabled())


def model_check_result() -> dict[str, Any] | None:
    mc = load_automation().get("model_check")
    return mc if isinstance(mc, dict) else None


def recap_model_ready() -> bool:
    mc = model_check_result()
    if mc is None:
        return True
    return bool(mc.get("ok"))


def _parse_checked_at(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def refresh_model_check(
    *,
    model: str = DEFAULT_MODEL,
    max_age_seconds: int = MODEL_CHECK_MAX_AGE_SECONDS,
    force: bool = False,
) -> dict[str, Any]:
    """Run or reuse cached Claude/Haiku probe; persist on automation.json."""
    state = load_automation()
    existing = state.get("model_check")
    if not force and isinstance(existing, dict) and existing.get("checked_at"):
        checked = _parse_checked_at(str(existing["checked_at"]))
        if checked is not None:
            age = (datetime.now(timezone.utc) - checked.astimezone(timezone.utc)).total_seconds()
            if age < max_age_seconds:
                return existing
    result = check_recap_model(model)
    state["model_check"] = result
    state["model_check_updated_at"] = _now_iso()
    save_automation(state)
    return result


def status_lines() -> list[str]:
    """Cockpit / doctor glance — one line per concern."""
    state = load_automation()
    enabled = bool(state.get("enabled", True))
    paused = bool(state.get("paused"))
    no_claude = bool(state.get(AUTO_DISABLED_NO_CLAUDE)) or not claude_on_path()
    # \[ escapes the literal bracket for this function's one real consumer,
    # cockpit/activity.py, which splices these lines into a Rich-markup
    # Static — unescaped, [o]/[p] parse as (unclosed) style tags and the
    # bracketed letters silently vanish from the rendered line. Confirmed
    # with rich.text.Text.from_markup()/Console.print().
    if no_claude and not enabled:
        lines = [
            "automation: off — claude not on PATH "
            "(assertions auto-propose disabled; Review still works for inbox)"
        ]
    elif not enabled:
        lines = [r"automation: off  \[o] turn on"]
    elif paused:
        lines = [r"automation: paused  \[p] resume  \[o] turn off"]
    else:
        lines = [r"automation: running  \[p] pause  \[o] turn off"]

    mc = model_check_result()
    if mc is None:
        lines.append(f"recap model: not checked yet ({DEFAULT_MODEL})")
    elif mc.get("ok"):
        lines.append(f"recap model: ok ({mc.get('model', DEFAULT_MODEL)})")
    else:
        detail = str(mc.get("detail") or "unavailable")[:80]
        lines.append(f"recap model: unavailable — {detail}")
    return lines


def status_line() -> str:
    """Single-line summary (legacy callers)."""
    return status_lines()[0]
