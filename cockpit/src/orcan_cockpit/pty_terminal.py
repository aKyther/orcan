"""Vendored pty+pyte terminal widget — embeds a live child process (in
practice: `tmux attach`) inside the Textual app, as OUR child under OUR own
pty. tmux keeps 100% of session/window/pane control; this widget only
relays bytes both ways and propagates resize.

Written in-repo rather than depending on the third-party `textual-terminal`
PyPI package: that package is unmaintained (~70 weekly downloads at time of
writing) and this is the single most load-bearing piece of the cockpit, so
it isn't worth the upstream risk. `pyte` (the VT100 screen-emulation library
`textual-terminal` itself wraps) is actively maintained and used directly.

v1 limitation: renders pyte's plain-text screen buffer only — no ANSI color
in the *render*. tmux's own colors/styles inside the session are unaffected
(this widget only relays raw bytes to/from the pty; nothing is stripped),
this just means the cockpit's own display of that buffer is monochrome for
now. Extending render() to walk pyte.Screen.buffer's per-cell Char objects
(fg/bg/bold/underline) is the natural v2 follow-up.
"""

from __future__ import annotations

import fcntl
import os
import pty
import struct
import subprocess
import termios
from typing import Sequence

import pyte
from rich.text import Text
from textual import events
from textual.widget import Widget

# Keys Textual normalizes away from raw bytes — mapped back to what a real
# terminal would send. C-Space is tmux's own prefix key (see
# docker/rootfs/etc/tmux/keybindings.conf) and MUST reach the child process,
# not be swallowed by the app — hence the explicit entry here.
_KEY_BYTES: dict[str, bytes] = {
    "enter": b"\r",
    "escape": b"\x1b",
    "tab": b"\t",
    "shift+tab": b"\x1b[Z",
    "backspace": b"\x7f",
    "up": b"\x1b[A",
    "down": b"\x1b[B",
    "right": b"\x1b[C",
    "left": b"\x1b[D",
    "home": b"\x1b[H",
    "end": b"\x1b[F",
    "delete": b"\x1b[3~",
    "pageup": b"\x1b[5~",
    "pagedown": b"\x1b[6~",
    "space": b" ",
    "ctrl+space": b"\x00",
}


def key_to_bytes(key: str, character: str | None) -> bytes | None:
    if key in _KEY_BYTES:
        return _KEY_BYTES[key]
    if key.startswith("ctrl+") and len(key) == 6 and key[5].isalpha():
        return bytes([ord(key[5].upper()) & 0x1F])
    if character:
        return character.encode("utf-8", errors="ignore")
    return None


class PtyTerminal(Widget):
    """Owns a pty; spawns `command` as a child attached to its slave end;
    relays bytes both ways; renders pyte's screen buffer."""

    can_focus = True

    def __init__(self, command: Sequence[str], *, env: dict[str, str] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._command = list(command)
        self._env = env
        self._master_fd: int | None = None
        self._process: subprocess.Popen | None = None
        self._screen: pyte.Screen | None = None
        self._stream: pyte.Stream | None = None

    def on_mount(self) -> None:
        self._spawn()
        self.set_interval(1 / 30, self._drain)
        self.focus()

    def on_unmount(self) -> None:
        self._close()

    def _term_size(self) -> tuple[int, int]:
        # At spawn time (on_mount) the widget's layout may not be computed
        # yet, giving size=(0, 0) — clamping that to 1x1 would start tmux in
        # a degenerate terminal it never recovers from until the next real
        # resize. Fall back to a standard 80x24 instead; the real on_resize
        # event (layout completing, or an actual terminal resize) corrects
        # it and triggers a proper tmux redraw either way.
        size = self.size
        rows = int(size.height) or 24
        cols = int(size.width) or 80
        return rows, cols

    @staticmethod
    def _set_winsize(fd: int, rows: int, cols: int) -> None:
        # Setting TIOCSWINSZ on either end of a pty pair makes the kernel
        # deliver SIGWINCH to the slave-side foreground process group
        # automatically — no manual signal plumbing needed.
        packed = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, packed)

    def _spawn(self) -> None:
        rows, cols = self._term_size()
        master_fd, slave_fd = pty.openpty()
        self._set_winsize(master_fd, rows, cols)
        self._process = subprocess.Popen(
            self._command,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=self._env,
            start_new_session=True,  # child becomes its own session/pgrp leader
            close_fds=True,
        )
        os.close(slave_fd)  # child holds its own duplicate; parent doesn't need it
        os.set_blocking(master_fd, False)
        self._master_fd = master_fd
        self._screen = pyte.Screen(cols, rows)
        self._stream = pyte.Stream(self._screen)

    def on_resize(self, event: events.Resize) -> None:
        if self._master_fd is None or self._screen is None:
            return
        rows, cols = self._term_size()
        self._screen.resize(rows, cols)
        self._set_winsize(self._master_fd, rows, cols)

    def _drain(self) -> None:
        if self._master_fd is None or self._stream is None:
            return
        try:
            data = os.read(self._master_fd, 65536)
        except BlockingIOError:
            return
        except OSError:
            self._close()
            return
        if not data:  # EOF — child exited (e.g. tmux session killed)
            self._close()
            return
        try:
            self._stream.feed(data.decode("utf-8", errors="replace"))
        except Exception:
            # pyte 0.8.2's Stream/Screen dispatch can raise on some
            # private-mode CSI sequences tmux sends on attach (e.g. a device
            # status query) — a bug in the emulation library's own
            # Stream<->Screen wiring, not our pty relay. Dropping one
            # escape sequence's effect is far better than losing the whole
            # embedded terminal over it.
            pass
        self.refresh()

    def on_key(self, event: events.Key) -> None:
        if self._master_fd is None:
            return
        data = key_to_bytes(event.key, event.character)
        if data is None:
            return
        event.stop()  # this widget owns the keyboard while focused
        try:
            os.write(self._master_fd, data)
        except OSError:
            pass

    def render(self) -> Text:
        if self._screen is None:
            return Text("(starting tmux…)")
        return Text("\n".join(self._screen.display))

    def _close(self) -> None:
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None
        if self._process is not None and self._process.poll() is None:
            try:
                self._process.terminate()
            except OSError:
                pass
        self._process = None
