"""Vendored pty+pyte terminal widget — embeds a live child process (in
practice: `tmux attach`) inside the Textual app, as OUR child under OUR own
pty. tmux keeps 100% of session/window/pane control; this widget only
relays bytes both ways and propagates resize.

**Not a native terminal.** Textual owns focus, selection, and mouse; tmux
expects xterm bytes on a PTY; pyte only emulates the visible screen. Each
input/output path needs an explicit translator — see sibling modules
``pty_keys``, ``pty_mouse``, ``pty_colors`` and docs
``docs/pl/guides/terminal-ui.md`` (section *Cockpit + przeglądarka*).

Written in-repo rather than depending on the third-party `textual-terminal`
PyPI package: that package is unmaintained (~70 weekly downloads at time of
writing) and this is the single most load-bearing piece of the cockpit, so
it isn't worth the upstream risk. `pyte` (the VT100 screen-emulation library
`textual-terminal` itself wraps) is actively maintained and used directly.

Renders pyte's per-cell Char buffer (fg/bg/bold/underline/etc., not just
plain text) into a styled Rich Text, so real ANSI colors (prompt themes,
`ls --color`, tmux's own status line) show up here the same as in a native
attach.
"""

from __future__ import annotations

import asyncio
import fcntl
import os
import pty
import struct
import subprocess
import termios
import time
from typing import Sequence

import pyte
from rich.color import Color
from rich.style import Style
from rich.text import Text
from textual import events
from textual.actions import SkipAction
from textual.message import Message
from textual.widget import Widget

from orcan_cockpit.pty_colors import pyte_color_to_rich as _pyte_color_to_rich_raw
from orcan_cockpit.pty_keys import esc_follow_up_bytes, key_to_bytes
from orcan_cockpit.pty_mouse import mouse_bytes, parse_mouse_modes

# pyte's fg/bg color values come in three shapes (see pyte.graphics /
# Screen.select_graphic_rendition): ANSI names (pyte uses classic terminfo
# "brown" for SGR 33 — Rich wants "yellow"), aixterm bright names
# ("brightred" / pyte "brightbrown" — Rich wants "bright_red" /
# "bright_yellow"), and bare 6-hex-digit strings with no leading "#" for
# 256-color / truecolor. Unknown tokens are dropped — see pty_colors.py.
def _pyte_color_to_rich(value: str) -> str | None:
    mapped = _pyte_color_to_rich_raw(value)
    if mapped is None:
        return None
    try:
        Color.parse(mapped)
    except Exception:
        return None
    return mapped


# Reused across cells/frames: most of a real terminal's content shares a
# handful of style combinations (default text + a few prompt/status
# accents), so building a fresh Style() per cell every frame would be a lot
# of avoidable churn on every keystroke's redraw.
_style_cache: dict[tuple, Style] = {}


def _char_style(char: "pyte.screens.Char") -> Style:
    fg, bg = char.fg, char.bg
    if char.reverse:
        fg, bg = bg, fg
    key = (fg, bg, char.bold, char.italics, char.underscore, char.strikethrough, char.blink)
    style = _style_cache.get(key)
    if style is None:
        style = Style(
            color=_pyte_color_to_rich(fg),
            bgcolor=_pyte_color_to_rich(bg),
            bold=char.bold,
            italic=char.italics,
            underline=char.underscore,
            strike=char.strikethrough,
            blink=char.blink,
        )
        _style_cache[key] = style
    return style


# When the user has a Textual text selection, these keys copy instead of going
# to tmux (otherwise Ctrl+C is SIGINT and the OS clipboard never updates).
_COPY_KEYS = frozenset({"ctrl+c", "ctrl+insert", "super+c", "ctrl+shift+c"})

# tmux toggles these on attach — see pty_mouse.parse_mouse_modes.
_ESC_COALESCE_S = 0.1


class PtyTerminal(Widget):
    """Owns a pty; spawns `command` as a child attached to its slave end;
    relays bytes both ways; renders pyte's screen buffer."""

    can_focus = True

    class Ready(Message):
        """Posted once, the first time real output arrives — the signal a
        parent uses to swap out its 'attaching…' loading indicator."""

        def __init__(self, pty_terminal: "PtyTerminal") -> None:
            self.pty_terminal = pty_terminal
            super().__init__()

    def __init__(self, command: Sequence[str], *, env: dict[str, str] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._command = list(command)
        self._env = env
        self._master_fd: int | None = None
        self._process: subprocess.Popen | None = None
        self._screen: pyte.Screen | None = None
        self._stream: pyte.Stream | None = None
        self._ready = False
        self._mouse_tracking = False
        self._mouse_sgr = True
        self._refresh_pending = False
        self._esc_coalesce_until: float | None = None

    @property
    def allow_vertical_scroll(self) -> bool:
        # Never let Textual eat wheel events — tmux owns scrollback.
        return False

    @property
    def allow_horizontal_scroll(self) -> bool:
        return False

    def on_mount(self) -> None:
        self._spawn()
        # Event-driven, not polled: a fixed-interval timer (however tight)
        # adds up to a full tick of latency between tmux writing output and
        # us reading it. add_reader wakes us the instant the fd is readable —
        # this is what made the embedded terminal feel laggy vs a native
        # tmux attach.
        assert self._master_fd is not None
        asyncio.get_running_loop().add_reader(self._master_fd, self._on_readable)
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

    @staticmethod
    def _make_controlling_tty() -> None:
        # Runs in the child, after start_new_session's setsid() but before
        # exec. Popen(stdin=slave_fd, ...) dup2s the slave onto fd 0 before
        # this callback runs, but merely inheriting an already-open pty fd
        # does NOT make it the session's controlling terminal (that only
        # happens implicitly when a session leader *opens* a tty path
        # itself). Without an explicit TIOCSCTTY here, the child has no
        # controlling terminal at all: TIOCSWINSZ on the master still updates
        # the shared winsize record, but the kernel has no foreground
        # process group to deliver SIGWINCH to, so tmux never notices a
        # resize happened and stays frozen at whatever size it saw at
        # attach — this is what made the embedded terminal never adapt to
        # its widget's size.
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)

    def _spawn(self) -> None:
        rows, cols = self._term_size()
        master_fd, slave_fd = pty.openpty()
        self._set_winsize(master_fd, rows, cols)
        env = dict(self._env) if self._env is not None else dict(os.environ)
        env.setdefault("TERM", "xterm-256color")
        self._process = subprocess.Popen(
            self._command,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=env,
            start_new_session=True,  # child becomes its own session/pgrp leader
            close_fds=True,
            preexec_fn=self._make_controlling_tty,
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

    def _note_mouse_modes(self, data: bytes) -> None:
        tracking, sgr = parse_mouse_modes(data)
        if tracking is not None:
            self._mouse_tracking = tracking
        if sgr is not None:
            self._mouse_sgr = sgr

    def _schedule_refresh(self) -> None:
        if self._refresh_pending:
            return
        self._refresh_pending = True
        self.call_later(self._flush_refresh)

    def _flush_refresh(self) -> None:
        self._refresh_pending = False
        self.refresh()

    def _on_readable(self) -> None:
        if self._master_fd is None or self._stream is None:
            return
        got_data = False
        while True:
            try:
                data = os.read(self._master_fd, 65536)
            except BlockingIOError:
                break
            except OSError:
                self._close()
                return
            if not data:  # EOF — child exited (e.g. tmux session killed)
                self._close()
                return
            got_data = True
            self._note_mouse_modes(data)
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
        if not got_data:
            return
        if not self._ready:
            self._ready = True
            self.post_message(self.Ready(self))
            # orcan tmux.conf always sets mouse on; if mode CSI was split
            # across reads, don't leave tracking disabled forever.
            if not self._mouse_tracking:
                self._mouse_tracking = True
            # xterm-256color + tmux mouse on → SGR (1006). Legacy X10 bytes
            # (button 64/65 = '@'/'A') echo as garbage when 1006 is expected.
            self._mouse_sgr = True
        self._schedule_refresh()

    def _write_pty(self, data: bytes) -> None:
        if self._master_fd is None:
            return
        try:
            os.write(self._master_fd, data)
        except OSError:
            pass

    def _cancel_esc_coalesce(self) -> None:
        self._esc_coalesce_until = None

    def _start_esc_coalesce(self) -> None:
        self._esc_coalesce_until = time.monotonic() + _ESC_COALESCE_S
        self.call_later(_ESC_COALESCE_S, self._flush_esc_coalesce)

    def _flush_esc_coalesce(self) -> None:
        if self._esc_coalesce_until is None:
            return
        if time.monotonic() < self._esc_coalesce_until:
            return
        self._write_pty(b"\x1b")
        self._cancel_esc_coalesce()

    def _flush_esc_if_pending(self) -> None:
        if self._esc_coalesce_until is None:
            return
        if time.monotonic() >= self._esc_coalesce_until:
            self._flush_esc_coalesce()

    def on_key(self, event: events.Key) -> None:
        if self._master_fd is None:
            return
        if event.key in _COPY_KEYS and self.text_selection is not None:
            try:
                self.screen.action_copy_text()
            except SkipAction:
                pass
            else:
                event.stop()
                return

        if self._esc_coalesce_until is not None:
            combined = esc_follow_up_bytes(event.key)
            if combined is not None and time.monotonic() < self._esc_coalesce_until:
                self._cancel_esc_coalesce()
                event.stop()
                self._write_pty(combined)
                return
            self._write_pty(b"\x1b")
            self._cancel_esc_coalesce()

        if event.key == "escape":
            self._start_esc_coalesce()
            event.stop()
            return

        data = key_to_bytes(event.key, event.character)
        if data is None:
            return
        event.stop()  # this widget owns the keyboard while focused
        self._write_pty(data)

    def on_paste(self, event: events.Paste) -> None:
        if self._master_fd is None:
            return
        event.stop()
        try:
            os.write(self._master_fd, event.text.encode("utf-8", errors="replace"))
        except OSError:
            pass

    def _write_mouse(
        self,
        event: events.MouseEvent,
        *,
        scroll: int | None = None,
        release: bool = False,
    ) -> None:
        if self._master_fd is None or not self._mouse_tracking:
            return
        rows, cols = self._term_size()
        data = mouse_bytes(
            event,
            scroll=scroll,
            release=release,
            rows=rows,
            cols=cols,
            sgr=self._mouse_sgr,
        )
        if data is None:
            return
        try:
            os.write(self._master_fd, data)
        except OSError:
            pass

    def _on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        self._write_mouse(event, scroll=64)
        event.stop()

    def _on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        self._write_mouse(event, scroll=65)
        event.stop()

    def _on_mouse_scroll_left(self, event: events.MouseScrollLeft) -> None:
        self._write_mouse(event, scroll=66)
        event.stop()

    def _on_mouse_scroll_right(self, event: events.MouseScrollRight) -> None:
        self._write_mouse(event, scroll=67)
        event.stop()

    def _on_mouse_down(self, event: events.MouseDown) -> None:
        # Forward without event.stop() so Textual drag-selection still works.
        self._write_mouse(event)

    def _on_mouse_up(self, event: events.MouseUp) -> None:
        self._write_mouse(event, release=True)

    def render(self) -> Text:
        if self._screen is None:
            return Text("(starting tmux…)")
        screen = self._screen
        out = Text()
        for y in range(screen.lines):
            line = screen.buffer[y]
            run_text: list[str] = []
            run_style: Style | None = None
            for x in range(screen.columns):
                char = line[x]
                style = _char_style(char)
                if run_style is not None and style == run_style:
                    run_text.append(char.data or " ")
                    continue
                if run_style is not None:
                    out.append("".join(run_text), style=run_style)
                run_text = [char.data or " "]
                run_style = style
            if run_style is not None:
                out.append("".join(run_text), style=run_style)
            if y != screen.lines - 1:
                out.append("\n")
        return out

    def _close(self) -> None:
        if self._master_fd is not None:
            try:
                asyncio.get_running_loop().remove_reader(self._master_fd)
            except (RuntimeError, ValueError, OSError):
                pass
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
