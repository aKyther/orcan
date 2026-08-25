"""Encode Textual mouse events as xterm SGR sequences for tmux.

Stdlib-only — host-testable. Tmux with `set -g mouse on` expects these on
the attached terminal (modes 1000/1006); the embedded PTY must synthesize them
because Textual consumes real mouse input for its own UI.
"""

from __future__ import annotations

import re
from typing import Protocol

# tmux toggles these on attach; order matters (reset often sends l then h).
_MOUSE_MODE_RE = re.compile(rb"\x1b\[\?(1000|1006)([hl])")


class _MouseLike(Protocol):
    x: int
    y: int
    button: int
    shift: bool
    meta: bool
    ctrl: bool


def _clamp(value: int, upper: int) -> int:
    if upper <= 0:
        return 0
    return min(max(value, 0), upper - 1)


def _sgr_button(event: _MouseLike, *, scroll: int | None, release: bool) -> int:
    if scroll is not None:
        button = scroll
    else:
        # Textual: 1=left, 2=middle, 3=right → SGR: 0, 1, 2
        button = max(0, event.button - 1)
        if release:
            button += 32
    if event.shift:
        button += 4
    if event.meta:
        button += 8
    if event.ctrl:
        button += 16
    return button


def _legacy_button(event: _MouseLike, *, scroll: int | None, release: bool) -> int:
    if scroll is not None:
        return scroll
    if release:
        button = 3
    else:
        button = max(0, event.button - 1)
    if event.shift:
        button += 4
    if event.meta:
        button += 8
    if event.ctrl:
        button += 16
    return button


def legacy_mouse_bytes(
    event: _MouseLike,
    *,
    scroll: int | None = None,
    release: bool = False,
    rows: int,
    cols: int,
) -> bytes | None:
    """X10 / normal mouse encoding (tmux when SGR mode 1006 is off)."""
    if cols <= 0 or rows <= 0:
        return None
    x = _clamp(event.x, cols) + 33  # 1-based column + 32
    y = _clamp(event.y, rows) + 33
    button = _legacy_button(event, scroll=scroll, release=release)
    return bytes([0x1B, ord("M"), button, x, y])


def sgr_mouse_bytes(
    event: _MouseLike,
    *,
    scroll: int | None = None,
    release: bool = False,
    rows: int,
    cols: int,
) -> bytes | None:
    if cols <= 0 or rows <= 0:
        return None
    x = _clamp(event.x, cols)
    y = _clamp(event.y, rows)
    button = _sgr_button(event, scroll=scroll, release=release)
    suffix = "m" if release else "M"
    return f"\x1b[<{button};{x + 1};{y + 1}{suffix}".encode("latin-1")


def mouse_bytes(
    event: _MouseLike,
    *,
    scroll: int | None = None,
    release: bool = False,
    rows: int,
    cols: int,
    sgr: bool = True,
) -> bytes | None:
    if sgr:
        return sgr_mouse_bytes(
            event, scroll=scroll, release=release, rows=rows, cols=cols
        )
    return legacy_mouse_bytes(
        event, scroll=scroll, release=release, rows=rows, cols=cols
    )


def parse_mouse_modes(data: bytes) -> tuple[bool | None, bool | None]:
    """Return final (tracking, sgr) states seen in *data* (None = unchanged)."""
    tracking: bool | None = None
    sgr: bool | None = None
    for mode, action in _MOUSE_MODE_RE.findall(data):
        enabled = action == b"h"
        if mode == b"1000":
            tracking = enabled
        elif mode == b"1006":
            sgr = enabled
    return tracking, sgr
