"""Console-script entry point (`orcan-cockpit`, see ../pyproject.toml
[project.scripts]). This is what ttyd's PTY command (cursor-ttyd) and
`orcan enter` / `cursor-launcher` ultimately run, via the thin bash shim at
docker/rootfs/usr/local/bin/agent-launcher — `exec
/opt/orcan-cockpit/venv/bin/orcan-cockpit`.

Interactive (real tty): launches the Textual cockpit app — a workspace
picker, then an embedded live tmux session (spawned as OUR child pty; tmux
itself still owns all session/window/pane state) with a side panel for
pending Context Assertions + actions. See app.py.

Non-interactive (piped/no tty — smoke tests, scripted use): prints the same
plain-text workspace menu the old bash agent-launcher did, reading choices
from stdin. No Textual app runs here — Textual requires a real terminal, and
this path must keep working under `docker compose run --no-TTY`
(tests/smoke/test-container.sh).
"""

from __future__ import annotations

import sys

# orcan.context_inbox is vendored (stdlib-only, shared with the separate
# orcan-context-review script) rather than packaged here — see __init__.py.
_VENDORED_LIB = "/usr/local/lib"


def main() -> int:
    if _VENDORED_LIB not in sys.path:
        sys.path.insert(0, _VENDORED_LIB)

    if not sys.stdin.isatty():
        from orcan_cockpit.picker import run_fallback_menu

        return run_fallback_menu()

    from orcan_cockpit.app import run_cockpit

    return run_cockpit()


if __name__ == "__main__":
    raise SystemExit(main())
