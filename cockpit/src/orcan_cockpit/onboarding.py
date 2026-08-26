"""First-run onboarding flag — stdlib-only (no Textual)."""

from __future__ import annotations

from pathlib import Path

FLAG_NAME = "cockpit-onboarding-done"


def onboarding_flag_path() -> Path:
    return Path.home() / ".local" / "share" / "orcan" / FLAG_NAME


def onboarding_already_seen() -> bool:
    return onboarding_flag_path().is_file()


def mark_onboarding_seen() -> None:
    path = onboarding_flag_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("1\n", encoding="utf-8")
    except OSError:
        pass
