"""Side-panel actions.

Deliberately stdlib-only (no Textual/pyte import) so it stays directly
unit-testable on the host, same convention as orcan.context_inbox.

Every action here is dispatched as a separate `tmux display-popup` against
the control plane — NEVER by writing into the embedded PtyTerminal's master
fd. That fd belongs to whatever's live in the attached pane; injecting
synthetic keystrokes into it would be fragile (depends on what's currently
running there) and is exactly what the user asked this cockpit not to do.
"""

from __future__ import annotations

import subprocess

REVIEW_COMMAND = "orcan-context-review; echo; read -p 'Press Enter to close…' _"


def context_review_popup_command(session: str) -> list[str]:
    return [
        "tmux",
        "display-popup",
        "-t",
        f"={session}",
        "-E",
        "-w",
        "80%",
        "-h",
        "80%",
        REVIEW_COMMAND,
    ]


def run_context_review_popup(session: str) -> subprocess.CompletedProcess:
    return subprocess.run(context_review_popup_command(session), check=False)
