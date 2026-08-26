"""Cockpit-side tmux navigation for chords that are painful to forward as
xterm bytes (Ctrl/Alt/Ctrl+Shift+arrows).

When Textual already has a clean Key event, call ``tmux select-pane`` /
``split-window`` against the attached session instead of synthesizing CSI /
legacy Meta for ``bind -n`` in keybindings.conf.

Many terminals (ttyd/xterm.js, Windows Terminal / WSL) deliver Alt+arrow as
Ctrl+arrow — Textual never sees distinct Meta. Cockpit therefore cannot keep
``keybindings.conf``'s Ctrl=split + Alt=focus on the same events. Mix:

- Ctrl/Alt+arrows → focus pane
- Ctrl+Shift+arrows → split pane

Raw ``orcan enter --tmux`` still uses conf (Ctrl=split, Alt=focus) when Meta
works. Escape+ctrl+arrow (browser/WSL Alt-as-Ctrl sequence) coalesces to focus.

Stdlib-only — host-testable without Textual.
"""

from __future__ import annotations

import subprocess

# Focus flags / split flags keyed by arrow direction.
_FOCUS: dict[str, tuple[str, ...]] = {
    "left": ("select-pane", "-L"),
    "right": ("select-pane", "-R"),
    "up": ("select-pane", "-U"),
    "down": ("select-pane", "-D"),
}
_SPLIT: dict[str, tuple[str, ...]] = {
    "left": ("split-window", "-h", "-b"),
    "right": ("split-window", "-h"),
    "up": ("split-window", "-v", "-b"),
    "down": ("split-window", "-v"),
}

_ARROW_DIRS = frozenset(_FOCUS)


def _build_nav_actions() -> dict[str, tuple[str, ...]]:
    actions: dict[str, tuple[str, ...]] = {}
    for direction, focus in _FOCUS.items():
        actions[f"alt+{direction}"] = focus
        actions[f"ctrl+{direction}"] = focus
        split = _SPLIT[direction]
        actions[f"ctrl+shift+{direction}"] = split
        actions[f"shift+ctrl+{direction}"] = split
    return actions


# Textual key → tmux argv after ``tmux`` (target ``-t`` added by nav_argv).
_NAV_ACTIONS: dict[str, tuple[str, ...]] = _build_nav_actions()


def nav_action(key: str) -> tuple[str, ...] | None:
    """Return tmux subcommand args for *key*, or None if not a cockpit-nav chord."""
    return _NAV_ACTIONS.get(key)


def esc_follow_up_nav_key(follow_key: str) -> str | None:
    """Map Textual's ``Escape`` + *follow_key* to a nav key (pane focus).

    Bare arrow after Escape → Meta+arrow (focus pane).
    Escape + ctrl+arrow (Windows Terminal / WSL) → also focus.
    Escape + ctrl+shift+arrow is left to the normal key path (split via
    ``nav_action`` when Textual reports the chord without Escape).
    """
    if follow_key.startswith(("ctrl+shift+", "shift+ctrl+")):
        return None
    if follow_key in _ARROW_DIRS:
        return f"alt+{follow_key}"
    if follow_key.startswith("ctrl+") and follow_key[5:] in _ARROW_DIRS:
        return f"alt+{follow_key[5:]}"
    return None


def nav_argv(session: str, key: str) -> list[str] | None:
    """Full ``tmux … -t =session:`` argv for *key*, or None if not intercepted."""
    action = nav_action(key)
    if action is None:
        return None
    # ``=name:`` = exact session, active window/pane. Bare ``=name`` works for
    # ``attach`` / ``display-popup`` but ``split-window`` / ``select-pane``
    # resolve ``-t`` as a *pane* and fail with "can't find pane: =name".
    return ["tmux", *action, "-t", f"={session}:"]


def run_nav(session: str, key: str) -> bool:
    """Run the nav command for *key*. True if this key was a nav chord."""
    argv = nav_argv(session, key)
    if argv is None:
        return False
    subprocess.run(argv, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True
