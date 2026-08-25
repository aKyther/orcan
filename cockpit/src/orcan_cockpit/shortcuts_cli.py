"""Standalone plain-text shortcut reference — `python3 -m orcan_cockpit.shortcuts_cli`.

Run inside a `tmux display-popup` (see keybindings.conf's `bind ?`) so it
works whether or not the Textual cockpit is running: a raw `tmux attach` or
`orcan enter --tmux` user gets the same shortcut reference as a cockpit user,
because both read the exact same SHORTCUTS manifest as shortcuts_modal.py.

Deliberately stdlib-only (no Textual import) — this must run as a plain
one-shot script inside a tmux popup, not a Textual app.
"""

from __future__ import annotations

from orcan_cockpit.shortcuts import EMBED_DISCLAIMER, format_row, grouped_by_layer


def render_plaintext() -> str:
    groups = grouped_by_layer()
    lines = ["orcan shortcuts", "─" * 40, ""]
    lines.append("APP")
    for shortcut in groups["app"]:
        lines.append("  " + format_row(shortcut))
    lines.append("")
    lines.append("TMUX (prefix = Ctrl+Space)")
    for shortcut in groups["tmux"]:
        lines.append("  " + format_row(shortcut))
    lines.append("")
    lines.append("─" * 40)
    lines.append(EMBED_DISCLAIMER)
    lines.append("Press Enter to close…")
    return "\n".join(lines) + "\n"


def main() -> int:
    print(render_plaintext(), end="")
    input()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
