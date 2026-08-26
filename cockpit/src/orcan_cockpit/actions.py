"""Side-panel actions.

Deliberately stdlib-only (no Textual/pyte import) so it stays directly
unit-testable on the host, same convention as orcan.context_inbox.

Every action here is dispatched as tmux control-plane commands — NEVER by
writing into the embedded PtyTerminal's master fd. That fd belongs to
whatever's live in the attached pane; injecting synthetic keystrokes into it
would be fragile (depends on what's currently running there) and is exactly
what the user asked this cockpit not to do.

Context automation toggles flip JSON flags on the history bind (see
orcan.automation) — no tmux popup needed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REVIEW_COMMAND = "orcan-context-review; echo; read -p 'Press Enter to close…' _"

# Host unit tests / image: orcan lib under /usr/local/lib or checkout rootfs.
for _lib in (
    Path("/usr/local/lib"),
    Path(__file__).resolve().parents[3] / "docker" / "rootfs" / "usr" / "local" / "lib",
):
    if (_lib / "orcan" / "automation.py").is_file():
        sys.path.insert(0, str(_lib))
        break

from orcan.automation import is_enabled, is_paused, status_lines, toggle_enabled, toggle_paused  # noqa: E402


def context_review_popup_command(session: str) -> list[str]:
    return [
        "tmux",
        "split-window",
        "-v",
        "-P",
        "-F",
        "#{pane_id}",
        "-t",
        f"={session}:",
        REVIEW_COMMAND,
    ]


def run_context_review_popup(session: str) -> subprocess.CompletedProcess:
    # Pane border / window tab pick up "review" via pane-label.sh (cmdline
    # contains orcan-context-review) — do not pin select-pane -T.
    return subprocess.run(
        context_review_popup_command(session),
        check=False,
        capture_output=True,
        text=True,
    )


def toggle_automation_pause() -> dict:
    """Flip pause flag (no-op when automation is turned off)."""
    return toggle_paused()


def toggle_automation_enabled() -> dict:
    """Master on/off for background context automation."""
    return toggle_enabled()


def automation_state() -> dict:
    """Read-only current enabled/paused state — for labeling toggle buttons
    without flipping anything (toggle_automation_pause/enabled do the
    flipping)."""
    return {"enabled": is_enabled(), "paused": is_paused()}


def automation_status_line() -> str:
    return "\n".join(status_lines())


def automation_status_lines() -> list[str]:
    return status_lines()
