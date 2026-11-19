"""Console-script entry point (`orcan-cockpit`, see ../pyproject.toml
[project.scripts]). This is what ttyd's PTY command (cursor-ttyd) and
`orcan enter` / `cursor-launcher` ultimately run, via the thin bash shim at
docker/rootfs/usr/local/bin/agent-launcher — `exec
/opt/orcan/plugins/cockpit/.venv/bin/orcan-cockpit`.

Interactive (real tty): launches the Textual cockpit app — a workspace
picker, then an embedded live tmux session (spawned as OUR child pty; tmux
itself still owns all session/window/pane state); see app.py.

Non-interactive (piped/no tty — smoke tests, scripted use): prints the same
plain-text workspace menu the old bash agent-launcher did, reading choices
from stdin. No Textual app runs here — Textual requires a real terminal, and
this path must keep working under `docker compose run --no-TTY`
(tests/smoke/test-container.sh).
"""

from __future__ import annotations

import sys


def _configure_terminal_input() -> None:
    # Keep this process-local: exporting Textual's environment setting would
    # also change keyboard handling in applications launched inside tmux.
    from textual import constants

    constants.DISABLE_KITTY_KEY = True


def main() -> int:
    if not sys.stdin.isatty():
        from orcan_cockpit.picker import run_fallback_menu

        return run_fallback_menu()

    # Textual's Kitty associated-text parser drops Alt from printable keys
    # (e.g. CSI 99;3;99u becomes plain "c"). Use legacy Meta input for the
    # embedded terminal; configure this before starting the terminal driver.
    _configure_terminal_input()

    from orcan_cockpit.app import run_cockpit

    return run_cockpit()


if __name__ == "__main__":
    raise SystemExit(main())
