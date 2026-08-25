"""Check whether in-container recap can call ``claude -p --model haiku``.

Used by ``orcan-context-scan`` (skip recap when unavailable), cockpit/doctor
glance lines, and ``orcan-context-model-check``. Result is cached in
``automation.json`` (``model_check`` field) so the UI does not probe every
refresh.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any


DEFAULT_MODEL = "haiku"
PROBE_PROMPT = "Reply with exactly: OK"
PROBE_TIMEOUT = 30


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def check_recap_model(model: str = DEFAULT_MODEL, *, probe: bool | None = None) -> dict[str, Any]:
    """Return ``{ok, detail, model, checked_at}`` — never raises."""
    if probe is None:
        probe = os.environ.get("ORCAN_CONTEXT_MODEL_PROBE", "1") != "0"

    claude = shutil.which("claude")
    if not claude:
        return {
            "ok": False,
            "detail": "claude not on PATH (recap/recap-review need Claude Code in container)",
            "model": model,
            "checked_at": _now_iso(),
        }

    try:
        ver = subprocess.run(
            [claude, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "detail": f"claude --version failed: {exc}",
            "model": model,
            "checked_at": _now_iso(),
        }
    if ver.returncode != 0:
        detail = (ver.stderr or ver.stdout or "unknown error").strip()[:200]
        return {
            "ok": False,
            "detail": f"claude --version exited {ver.returncode}: {detail}",
            "model": model,
            "checked_at": _now_iso(),
        }

    if not probe:
        detail = (ver.stdout or ver.stderr or "claude present").strip().splitlines()[0][:120]
        return {"ok": True, "detail": detail, "model": model, "checked_at": _now_iso()}

    try:
        result = subprocess.run(
            [claude, "-p", "--model", model, PROBE_PROMPT],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "detail": f"claude -p --model {model} probe failed: {exc}",
            "model": model,
            "checked_at": _now_iso(),
        }
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown error").strip()[:200]
        return {
            "ok": False,
            "detail": f"claude -p exited {result.returncode}: {detail}",
            "model": model,
            "checked_at": _now_iso(),
        }
    return {
        "ok": True,
        "detail": f"probe ok ({model})",
        "model": model,
        "checked_at": _now_iso(),
    }
