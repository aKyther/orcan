"""Vendored pty+pyte terminal widget — embeds a live child process (in
practice: `tmux attach`) inside the Textual app, as OUR child under OUR own
pty. tmux keeps 100% of session/window/pane control; this widget mostly
relays bytes both ways and propagates resize.

**Nav mix:** Ctrl/Alt+arrows (and Escape+arrow coalesce) call the matching
tmux pane action via ``pty_tmux_nav`` when a session name is set — no CSI/Meta
synthesis. Escape+ctrl+arrow is treated as browser/WSL Alt+arrow.
Other keys still forward through ``pty_keys``. ``keybindings.conf`` is
unchanged for raw ``tmux attach``.

**Not a native terminal.** Textual owns focus, selection, and mouse; tmux
expects xterm bytes on a PTY; pyte only emulates the visible screen. Each
input/output path needs an explicit translator — see sibling modules
``pty_keys``, ``pty_mouse``, ``pty_colors``, ``pty_tmux_nav``, ``pty_links`` and docs
``docs/en/guides/terminal-ui.md`` (section *Cockpit + browser*).

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
import codecs
import fcntl
import os
import pty
import struct
import subprocess
import tempfile
import termios
import time
from collections import deque
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pyte
from rich.color import Color
from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual import events
from textual.actions import SkipAction
from textual.geometry import Region
from textual.message import Message
from textual.strip import Strip
from textual.timer import Timer
from textual.widget import Widget

from orcan_cockpit.pty_colors import pyte_color_to_rich as _pyte_color_to_rich_raw
from orcan_cockpit.pty_keys import esc_follow_up_bytes, key_to_bytes
from orcan_cockpit.pty_links import (
    annotate_plain_urls,
    attach_hyperlink_screen,
    feed_with_osc8,
    normalize_wide_cells,
    open_url,
    url_at_screen,
)
from orcan_cockpit.pty_mouse import mouse_bytes
from orcan_cockpit.pty_tmux_nav import esc_follow_up_nav_key, nav_action, run_nav


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
_STYLE_CACHE_LIMIT = 4096


@lru_cache(maxsize=_STYLE_CACHE_LIMIT)
def _cached_style(
    fg, bg, bold, italics, underscore, strikethrough, blink, reverse, link
) -> Style:
    # Let Rich resolve reverse against the outer terminal's default colors.
    # Swapping two "default" color names loses reverse-video entirely.
    return Style(
        color=_pyte_color_to_rich(fg),
        bgcolor=_pyte_color_to_rich(bg),
        bold=bold,
        italic=italics,
        underline=underscore or bool(link),
        strike=strikethrough,
        blink=blink,
        reverse=reverse,
        link=link,
    )


def _char_style(char: pyte.screens.Char, link: str | None = None) -> Style:
    return _cached_style(
        char.fg,
        char.bg,
        char.bold,
        char.italics,
        char.underscore,
        char.strikethrough,
        char.blink,
        char.reverse,
        link,
    )


def _overlay_style(strip: Strip, start: int, end: int, style: Style) -> Strip:
    """Apply cursor/selection above existing cell styles, not underneath."""
    middle = strip.crop(start, end)
    return Strip.join(
        [
            strip.crop(0, start),
            Strip(Segment.apply_style(middle, post_style=style), middle.cell_length),
            strip.crop(end),
        ]
    )


# When the user has a Textual text selection, these keys copy instead of going
# to tmux (otherwise Ctrl+C is SIGINT and the OS clipboard never updates).
_COPY_KEYS = frozenset({"ctrl+c", "ctrl+insert", "super+c", "ctrl+shift+c"})

# F1–F5 are cockpit chrome (shortcuts, panels, peek) — let them bubble when
# unmapped; swallow other unknown keys so they do not hit browser / Screen binds.
_COCKPIT_FUNCTION_KEYS = frozenset({"f1", "f2", "f3", "f4", "f5"})

# Ctrl+[ is Esc on real terminals — Textual names it ctrl+left_square_brace.
_ESCAPE_KEYS = frozenset({"escape", "ctrl+left_square_brace"})

# Match context_tui's curses escdelay (25ms): long enough to recombine
# Textual's Escape+key pairs for Meta/Alt, short enough that bare Esc in
# vim/shell feels immediate.
_ESC_COALESCE_S = 0.025
_STAGED_PASTE_MAX_AGE_S = 24 * 60 * 60
# A busy agent can write continuously (build logs, test output, streaming
# responses). Drain enough to keep the terminal current, then yield so input,
# resize, and Textual chrome are not starved by one readable-fd callback.
_MAX_READ_BYTES_PER_TICK = 256 * 1024
_CURSOR_BLINK_S = 0.5
_CURSOR_STYLE = Style(reverse=True)
_CURSOR_UNREVERSE_STYLE = Style(reverse=False)
# pyte shifts DEC private mode numbers by five bits in Screen.mode.
_MOUSE_TRACKING_MODES = (1000 << 5, 1002 << 5, 1003 << 5)
_SGR_MOUSE_MODE = 1006 << 5
_BRACKETED_PASTE_MODE = 2004 << 5
_NAV_QUEUE_LIMIT = 32
_INPUT_QUEUE_BYTES_LIMIT = 1024 * 1024
# Keep ordinary large pastes intact for the receiving agent. Only payloads
# exceeding the entire input budget need the private-file fallback.
_STAGED_PASTE_BYTES = _INPUT_QUEUE_BYTES_LIMIT - 12 + 1
_INPUT_QUEUE_ITEMS_LIMIT = 4096
_INPUT_DRAIN_TIMEOUT_S = 2.0


class PtyTerminal(Widget):
    """Owns a pty; spawns `command` as a child attached to its slave end;
    relays bytes both ways; renders pyte's screen buffer."""

    can_focus = True

    class Ready(Message):
        """Posted once, the first time real output arrives — the signal a
        parent uses to swap out its 'attaching…' loading indicator."""

        def __init__(self, pty_terminal: PtyTerminal) -> None:
            self.pty_terminal = pty_terminal
            super().__init__()

    def __init__(
        self,
        command: Sequence[str],
        *,
        session: str | None = None,
        env: dict[str, str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        from orcan_cockpit.probe import SingleFlightProbe
        from orcan_cockpit.runtime_limits import limits

        self._link_probe = SingleFlightProbe()
        self._io_limits = limits()
        self._command = list(command)
        self._session = session
        self._env = env
        self._master_fd: int | None = None
        self._process: subprocess.Popen | None = None
        self._screen: pyte.Screen | None = None
        self._stream: pyte.Stream | None = None
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._read_resume: asyncio.TimerHandle | None = None
        self._ready = False
        self._mouse_tracking = False
        self._mouse_sgr = False
        self._nav_queue: deque[tuple[str, object]] = deque()
        self._input_queue_bytes = 0
        self._write_drained = asyncio.Event()
        self._write_drained.set()
        self._write_error = False
        self._nav_running = False
        self._nav_worker = None
        self._esc_coalesce_until: float | None = None
        self._esc_coalesce_timer: Timer | None = None
        # The master PTY is non-blocking. A single os.write() is permitted to
        # accept only a prefix, which used to truncate large bracketed pastes
        # before their closing marker reached tmux.
        self._write_buffer = bytearray()
        self._write_watch_installed = False
        # Per-line render cache — only pyte's dirty rows are rebuilt each
        # paint (typing, spinners and status ticks touch a line or two; a
        # full rebuild every frame is what made scroll / heavy output lag).
        # NB: must not be named `_render_cache` — Textual's Widget owns that
        # attribute for its own strip cache (a `_RenderCache` namedtuple).
        # Sharing the name let a no-output repaint (e.g. a click) return
        # Textual's namedtuple from render() → "VisualError: unable to
        # display '_RenderCache' type".
        self._line_cache: list[Text] = []
        self._frame_cache: Text | None = None
        self._strip_cache: dict[int, Strip] = {}
        self._cache_size = (0, 0)
        self._painted_cursor_row: int | None = None
        # pyte tracks the cursor position but does not render it. Keep the
        # terminal's familiar block cursor here, independent of whether its
        # child is zsh, Codex, Claude Code, vim, or another TUI.
        self._cursor_visible = True
        self._cursor_timer: Timer | None = None

    @property
    def allow_vertical_scroll(self) -> bool:
        # Never let Textual eat wheel events — tmux owns scrollback.
        return False

    @property
    def allow_horizontal_scroll(self) -> bool:
        return False

    def on_mount(self) -> None:
        # Expire files left by a prior browser session even when the user does
        # not paste again in this session.
        self._purge_staged_pastes()
        self._spawn()
        self._cursor_timer = self.set_interval(
            _CURSOR_BLINK_S,
            self._toggle_cursor,
            name="pty-cursor-blink",
        )
        # Event-driven, not polled: a fixed-interval timer (however tight)
        # adds up to a full tick of latency between tmux writing output and
        # us reading it. add_reader wakes us the instant the fd is readable —
        # this is what made the embedded terminal feel laggy vs a native
        # tmux attach.
        assert self._master_fd is not None
        asyncio.get_running_loop().add_reader(self._master_fd, self._on_readable)
        self.focus()

    def on_focus(self, _event: events.Focus) -> None:
        self._cursor_visible = True
        self.refresh()

    def on_blur(self, _event: events.Blur) -> None:
        self._cursor_visible = False
        self.refresh()

    def on_unmount(self) -> None:
        self._close()

    def _toggle_cursor(self) -> None:
        if not self.has_focus:
            return
        self._cursor_visible = not self._cursor_visible
        self._refresh_cursor_rows()

    @staticmethod
    def _cursor_offset(
        screen: pyte.Screen, cols: int, *, focused: bool, visible: bool
    ) -> int | None:
        """Return the Rich-text offset for pyte's cursor, if it should show."""
        cursor = screen.cursor
        if not focused or not visible or cursor.hidden:
            return None
        if not (0 <= cursor.x < cols and 0 <= cursor.y < screen.lines):
            return None
        normalize_wide_cells(screen, range(cursor.y + 1))
        # Rich text contains one newline after every screen row except the
        # final one. Count text codepoints, not display cells: wide glyphs
        # have an empty continuation cell and combining marks share a cell.
        column = cursor.x
        if column and not screen.buffer[cursor.y][column].data:
            column -= 1
        return (
            sum(
                len(screen.buffer[y][x].data)
                for y in range(cursor.y)
                for x in range(cols)
            )
            + cursor.y
            + sum(len(screen.buffer[cursor.y][x].data) for x in range(column))
        )

    def _render_cursor(self, frame: Text, screen: pyte.Screen, cols: int) -> Text:
        offset = self._cursor_offset(
            screen,
            cols,
            focused=self.has_focus,
            visible=self._cursor_visible,
        )
        if offset is not None:
            column = screen.cursor.x
            if column and not screen.buffer[screen.cursor.y][column].data:
                column -= 1
            cell = screen.buffer[screen.cursor.y][column]
            style = _CURSOR_UNREVERSE_STYLE if cell.reverse else _CURSOR_STYLE
            frame.stylize(style, offset, offset + max(1, len(cell.data)))
        return frame

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
        HyperlinkScreen, Stream = attach_hyperlink_screen(
            lambda data: self._send_pty(data.encode("ascii"))
        )
        self._screen = HyperlinkScreen(cols, rows)
        self._stream = Stream(self._screen)

    def on_resize(self, event: events.Resize) -> None:
        if self._master_fd is None or self._screen is None:
            return
        rows, cols = self._term_size()
        self._screen.resize(rows, cols)
        self._set_winsize(self._master_fd, rows, cols)
        # Column count changed → every cached line is the wrong width.
        self._line_cache = []
        self._strip_cache.clear()
        self._cache_size = (0, 0)
        self._frame_cache = None
        self.refresh()

    def _sync_terminal_modes(self) -> None:
        # Read the incremental VT parser's state, including grouped DECSET
        # commands and sequences split between any two PTY reads.
        if self._screen is not None:
            modes = self._screen.mode
            self._mouse_tracking = any(mode in modes for mode in _MOUSE_TRACKING_MODES)
            self._mouse_sgr = _SGR_MOUSE_MODE in modes

    def _schedule_refresh(self) -> None:
        # Paint on the next idle immediately. Do not go through call_later —
        # that waits until this widget's *entire* message queue drains, which
        # visibly lags full-screen CSI clears (shell `clear`) whenever
        # metrics/status intervals are also posting. refresh() already
        # coalesces multiple calls and wakes the idle pump (check_idle).
        if self._screen is None:
            return
        if self._cache_size != (self._screen.lines, self._screen.columns):
            self.refresh()
        else:
            for y in self._screen.dirty:
                self.refresh(Region(0, y, self._screen.columns, 1))
            self._refresh_cursor_rows()

    def _refresh_cursor_rows(self) -> None:
        screen = self._screen
        if screen is None:
            return
        for y in {self._painted_cursor_row, screen.cursor.y}:
            if y is not None and 0 <= y < screen.lines:
                self.refresh(Region(0, y, screen.columns, 1))
        self._painted_cursor_row = screen.cursor.y

    def _feed_output(self, data: bytes, *, final: bool = False) -> bool:
        text = self._decoder.decode(data, final=final)
        if text:
            feed_with_osc8(
                self._stream, self._screen, text, on_clipboard=self._copy_from_child
            )
        return bool(text)

    def _on_readable(self) -> None:
        if self._master_fd is None or self._stream is None:
            return
        got_data = False
        drained = False
        ended = False
        bytes_read = 0
        budget = self._io_limits["pty_read_bytes"]
        deadline = time.monotonic() + self._io_limits["pty_read_ms"] / 1000
        while bytes_read < budget and (bytes_read == 0 or time.monotonic() < deadline):
            try:
                data = os.read(
                    self._master_fd,
                    min(self._io_limits["pty_chunk_bytes"], budget - bytes_read),
                )
            except BlockingIOError:
                drained = True
                break
            except OSError:
                ended = True
                break
            if not data:  # EOF — child exited (e.g. tmux session killed)
                ended = True
                break
            got_data = True
            bytes_read += len(data)
            try:
                self._feed_output(data)
            except Exception:
                # pyte 0.8.2's Stream/Screen dispatch can raise on some
                # private-mode CSI sequences tmux sends on attach (e.g. a device
                # status query) — a bug in the emulation library's own
                # Stream<->Screen wiring, not our pty relay. Dropping one
                # escape sequence's effect is far better than losing the whole
                # embedded terminal over it.
                pass
        if ended:
            got_data = self._feed_output(b"", final=True) or got_data
            self._close()
        if not got_data:
            return
        self._sync_terminal_modes()
        if not self._ready:
            self._ready = True
            self.post_message(self.Ready(self))
        self._schedule_refresh()
        if not ended and not drained and self._read_resume is None:
            # A level-triggered fd stays ready throughout an output flood.
            # A per-callback budget alone gives the UI no quiet turn to paint.
            # Leave bytes in the PTY (kernel backpressure, no output loss) and
            # briefly release the loop before resuming event-driven reads.
            loop = asyncio.get_running_loop()
            loop.remove_reader(self._master_fd)
            self._read_resume = loop.call_later(1 / 120, self._resume_pty_read)

    def _resume_pty_read(self) -> None:
        self._read_resume = None
        if self._master_fd is not None:
            asyncio.get_running_loop().add_reader(self._master_fd, self._on_readable)

    def _write_pty(self, data: bytes) -> None:
        if self._nav_running:
            self._queue_input("data", data)
        else:
            self._send_pty(data)

    def _send_pty(self, data: bytes) -> None:
        if self._master_fd is None or not data:
            return
        if not self._input_fits(len(data)):
            return
        self._write_drained.clear()
        self._write_buffer.extend(data)
        self._flush_pty_write()

    def _watch_pty_writable(self) -> None:
        if self._master_fd is None or self._write_watch_installed:
            return
        try:
            asyncio.get_running_loop().add_writer(
                self._master_fd, self._flush_pty_write
            )
        except (RuntimeError, TypeError, ValueError, OSError):
            return
        self._write_watch_installed = True

    def _unwatch_pty_writable(self) -> None:
        if not self._write_watch_installed:
            return
        try:
            asyncio.get_running_loop().remove_writer(self._master_fd)
        except (RuntimeError, TypeError, ValueError, OSError):
            pass
        self._write_watch_installed = False

    def _flush_pty_write(self) -> None:
        """Write all currently accepted input, retrying when the PTY is full."""
        if self._master_fd is None:
            self._write_buffer.clear()
            self._write_drained.set()
            self._unwatch_pty_writable()
            return
        while self._write_buffer:
            try:
                written = os.write(self._master_fd, self._write_buffer)
            except BlockingIOError:
                self._watch_pty_writable()
                return
            except OSError:
                self._write_error = True
                self._write_buffer.clear()
                self._write_drained.set()
                self._unwatch_pty_writable()
                return
            if written <= 0:
                self._watch_pty_writable()
                return
            del self._write_buffer[:written]
        self._write_drained.set()
        self._unwatch_pty_writable()

    def _cancel_esc_coalesce(self) -> None:
        self._esc_coalesce_until = None
        if self._esc_coalesce_timer is not None:
            self._esc_coalesce_timer.stop()
            self._esc_coalesce_timer = None

    def _schedule_esc_coalesce_flush(self, delay: float) -> None:
        if self._esc_coalesce_timer is not None:
            self._esc_coalesce_timer.stop()
        self._esc_coalesce_timer = self.set_timer(
            delay,
            self._flush_esc_coalesce,
            name="pty-esc-coalesce",
        )

    def _start_esc_coalesce(self) -> None:
        self._esc_coalesce_until = time.monotonic() + _ESC_COALESCE_S
        self._schedule_esc_coalesce_flush(_ESC_COALESCE_S)

    def _flush_esc_coalesce(self) -> None:
        if self._esc_coalesce_until is None or self._master_fd is None:
            self._cancel_esc_coalesce()
            return
        remaining = self._esc_coalesce_until - time.monotonic()
        if remaining > 0:
            # Timer may fire a hair early — reschedule instead of dropping Esc.
            self._schedule_esc_coalesce_flush(remaining)
            return
        self._write_pty(b"\x1b")
        self._cancel_esc_coalesce()

    def _flush_esc_if_pending(self) -> None:
        if self._esc_coalesce_until is None:
            return
        if time.monotonic() >= self._esc_coalesce_until:
            self._flush_esc_coalesce()

    def _queue_nav(self, key: str) -> bool:
        if self._session is None or nav_action(key) is None:
            return False
        if (
            sum(kind == "nav" for kind, _ in self._nav_queue) >= _NAV_QUEUE_LIMIT
            or len(self._nav_queue) >= _INPUT_QUEUE_ITEMS_LIMIT
        ):
            self.notify("Navigation queue is full; wait for tmux.", severity="warning")
            return True
        self._nav_queue.append(("nav", key))
        if not self._nav_running:
            self._nav_running = True
            self._nav_worker = self.run_worker(
                self._drain_nav, group="pty-navigation", exit_on_error=False
            )
        return True

    def _input_fits(self, size: int) -> bool:
        if (
            len(self._write_buffer) + self._input_queue_bytes + size
            <= _INPUT_QUEUE_BYTES_LIMIT
        ):
            return True
        self.notify("Input queue is full; this input was not sent.", severity="warning")
        return False

    @staticmethod
    def _queued_input_size(kind: str, payload) -> int:
        # Paste mode is resolved after navigation. Reserve both delimiters;
        # mouse reports have bounded coordinates but variable decimal widths.
        if kind == "paste":
            return len(payload) + 12
        if kind == "mouse":
            return 128
        return len(payload)

    def _queue_input(self, kind: str, payload) -> None:
        size = self._queued_input_size(kind, payload)
        if not self._input_fits(size):
            return
        if len(self._nav_queue) >= _INPUT_QUEUE_ITEMS_LIMIT:
            self.notify(
                "Input queue is full; this input was not sent.", severity="warning"
            )
            return
        if kind == "data" and self._nav_queue and self._nav_queue[-1][0] == "data":
            self._nav_queue[-1][1].extend(payload)
        else:
            self._nav_queue.append(
                (kind, bytearray(payload) if kind == "data" else payload)
            )
        self._input_queue_bytes += size

    async def _drain_nav(self) -> None:
        try:
            while self._nav_queue:
                kind, payload = self._nav_queue.popleft()
                try:
                    if kind == "nav":
                        await asyncio.wait_for(
                            self._write_drained.wait(), _INPUT_DRAIN_TIMEOUT_S
                        )
                        if self._write_error or self._master_fd is None:
                            raise OSError("PTY input is unavailable")
                        await run_nav(self._session, payload)
                    else:
                        self._input_queue_bytes -= self._queued_input_size(
                            kind, payload
                        )
                        if kind == "paste":
                            data = self._encode_paste(payload)
                        elif kind == "mouse":
                            data = self._encode_mouse(*payload)
                        else:
                            data = bytes(payload)
                        if data:
                            self._send_pty(data)
                except (OSError, TimeoutError, subprocess.CalledProcessError):
                    self._nav_queue.clear()
                    self._input_queue_bytes = 0
                    self.notify(
                        "Navigation failed; queued navigation and input were not sent.",
                        severity="warning",
                    )
        finally:
            self._nav_running = False

    def on_key(self, event: events.Key) -> None:
        self._cursor_visible = True
        if self._master_fd is None:
            if event.key not in _COCKPIT_FUNCTION_KEYS:
                event.stop()
            return
        self._flush_esc_if_pending()
        if event.key in _COPY_KEYS and self.text_selection is not None:
            try:
                self.screen.action_copy_text()
            except SkipAction:
                pass
            else:
                event.stop()
                return

        if self._esc_coalesce_until is not None:
            if (
                self._session
                and time.monotonic() < self._esc_coalesce_until
                and (nav_key := esc_follow_up_nav_key(event.key)) is not None
            ):
                self._cancel_esc_coalesce()
                event.stop()
                self._queue_nav(nav_key)
                return
            combined = esc_follow_up_bytes(event.key)
            if combined is not None and time.monotonic() < self._esc_coalesce_until:
                self._cancel_esc_coalesce()
                event.stop()
                self._write_pty(combined)
                return
            self._write_pty(b"\x1b")
            self._cancel_esc_coalesce()

        if event.key in _ESCAPE_KEYS:
            self._start_esc_coalesce()
            event.stop()
            return

        # Ctrl/Alt+arrows: drive tmux directly when we know the session —
        # skip CSI/Meta PTY writes (and avoid double-firing bind -n).
        if self._queue_nav(event.key):
            event.stop()
            return

        data = key_to_bytes(event.key, event.character)
        if data is None:
            if event.key not in _COCKPIT_FUNCTION_KEYS:
                event.stop()
            return
        event.stop()  # this widget owns the keyboard while focused
        self._write_pty(data)

    def _commit_pending_escape(self) -> None:
        if self._esc_coalesce_until is not None:
            self._write_pty(b"\x1b")
            self._cancel_esc_coalesce()

    def on_paste(self, event: events.Paste) -> None:
        self._cursor_visible = True
        if self._master_fd is None:
            return
        event.stop()
        self._commit_pending_escape()
        data = event.text.encode("utf-8", errors="replace")
        if len(data) < _STAGED_PASTE_BYTES:
            self._write_paste(data)
            return
        path = self._stage_large_paste(data)
        if path is None:
            # A failed staging attempt must not silently lose the user's input.
            self._write_paste(data)
            return
        prompt = (
            f"Large input ({len(data):,} bytes) saved to {path}. "
            "Read that file first, then continue with the request it contains."
        )
        self._write_paste(prompt.encode("utf-8"))

    def _write_paste(self, data: bytes) -> None:
        if self._nav_running:
            self._queue_input("paste", data)
            return
        self._write_pty(self._encode_paste(data))

    def _encode_paste(self, data: bytes) -> bytes:
        if self._screen is not None and _BRACKETED_PASTE_MODE in self._screen.mode:
            data = b"\x1b[200~" + data + b"\x1b[201~"
        return data

    @staticmethod
    def _purge_staged_pastes() -> None:
        """Best-effort expiry for files created by this widget only."""
        deadline = time.time() - _STAGED_PASTE_MAX_AGE_S
        try:
            for path in Path(tempfile.gettempdir()).glob("orcan-paste-*.md"):
                if path.is_file() and path.stat().st_mtime < deadline:
                    path.unlink()
        except OSError:
            pass

    def _stage_large_paste(self, data: bytes) -> str | None:
        self._purge_staged_pastes()
        fd = -1
        try:
            fd, path = tempfile.mkstemp(prefix="orcan-paste-", suffix=".md")
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as staged:
                fd = -1
                staged.write(data)
            return path
        except OSError:
            if fd >= 0:
                os.close(fd)
            return None

    def _copy_from_child(self, text: str) -> None:
        """A yank inside tmux (copy-mode ``y``, mouse drag, ``prefix u`` /
        ``prefix P``) emits OSC 52; pyte drops it, so relay it to the real
        outer terminal / browser via Textual's own clipboard write."""
        if not text:
            return
        try:
            self.app.copy_to_clipboard(text)
        except Exception:
            pass

    def _write_mouse(
        self,
        event: events.MouseEvent,
        *,
        scroll: int | None = None,
        release: bool = False,
    ) -> None:
        self._commit_pending_escape()
        if self._nav_running:
            snapshot = SimpleNamespace(
                **{
                    name: getattr(event, name)
                    for name in ("x", "y", "button", "shift", "meta", "ctrl")
                }
            )
            self._queue_input("mouse", (snapshot, scroll, release))
            return
        data = self._encode_mouse(event, scroll, release)
        if data:
            self._write_pty(data)

    def _encode_mouse(self, event, scroll, release) -> bytes | None:
        if self._master_fd is None or not self._mouse_tracking:
            return None
        rows, cols = self._term_size()
        return mouse_bytes(
            event,
            scroll=scroll,
            release=release,
            rows=rows,
            cols=cols,
            sgr=self._mouse_sgr,
        )

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

    def on_click(self, event: events.Click) -> None:
        # Clicks in the rendered tmux pane must keep keyboard focus here —
        # otherwise Esc and other keys bubble to the cockpit / browser.
        self.focus()
        # Textual owns the mouse, so OSC 8 / bare URLs never reach the outer
        # terminal's click-to-open. Open http(s) under the click ourselves.
        if event.button != 1:
            return
        url = event.style.link if event.style is not None else None
        if not url and self._screen is not None:
            url = url_at_screen(self._screen, int(event.x), int(event.y))
        if not url:
            return
        event.stop()
        self.run_worker(self._open_link(url), group="pty-link", exclusive=True)

    async def _open_link(self, url: str) -> None:
        # Browser helpers can wait for seconds, or wait indefinitely for an
        # external browser. Never run them in the terminal's message handler.
        if await self._link_probe.read(url, lambda: open_url(url)):
            return
        # Headless / ttyd: keep Style(link=) in the render so Ctrl+click on
        # the outer terminal may still work; surface the URL for copy.
        try:
            self.app.notify(f"Open URL: {url}", title="Link", timeout=8)
        except Exception:
            pass

    def _render_line(self, screen, y: int, cols: int, link_at) -> Text:
        normalize_wide_cells(screen, (y,))
        line = screen.buffer[y]
        line_text = "".join(line[x].data for x in range(cols))
        hrefs: list[str | None] = [None] * cols
        has_href = False
        if link_at is not None:
            for x in range(cols):
                href = link_at(x, y)
                if href is not None:
                    hrefs[x] = href
                    has_href = True
        # annotate_plain_urls scans the row with a regex — skip it entirely
        # for the overwhelmingly common line that holds no URL.
        if "http" in line_text:
            text_hrefs: list[str | None] = [None] * len(line_text)
            annotate_plain_urls(text_hrefs, line_text)
            offset = 0
            for x in range(cols):
                data = line[x].data
                if data and hrefs[x] is None:
                    hrefs[x] = text_hrefs[offset]
                offset += len(data)
            has_href = True
        out = Text()
        run_text: list[str] = []
        run_style: Style | None = None
        for x in range(cols):
            char = line[x]
            if not char.data:  # continuation cell of a double-width glyph
                continue
            style = _char_style(char, hrefs[x] if has_href else None)
            if run_style is not None and style == run_style:
                run_text.append(char.data or " ")
                continue
            if run_style is not None:
                out.append("".join(run_text), style=run_style)
            run_text = [char.data or " "]
            run_style = style
        if run_style is not None:
            out.append("".join(run_text), style=run_style)
        return out

    def _sync_lines(self) -> None:
        screen = self._screen
        if screen is None:
            return
        size = (screen.lines, screen.columns)
        if self._cache_size != size:
            self._line_cache = [Text() for _ in range(screen.lines)]
            self._strip_cache.clear()
            self._cache_size = size
            dirty = range(screen.lines)
        else:
            dirty = tuple(screen.dirty)
        link_at = getattr(screen, "link_at", None)
        for y in dirty:
            if 0 <= y < screen.lines:
                self._line_cache[y] = self._render_line(
                    screen, y, screen.columns, link_at
                )
                self._strip_cache.pop(y, None)
                self._frame_cache = None
        screen.dirty.clear()

    def render_line(self, y: int) -> Strip:
        """Paint one row; cursor and selection never rebuild the full frame."""
        screen = self._screen
        if screen is None:
            return super().render_line(y)
        self._sync_lines()
        if not 0 <= y < screen.lines:
            return Strip.blank(self.size.width, self.visual_style.rich_style)
        if y not in self._strip_cache:
            self._strip_cache[y] = (
                Strip(self._line_cache[y].render(self.app.console))
                .extend_cell_length(screen.columns)
                .crop(0, screen.columns)
            )
        strip = self._strip_cache[y]
        cursor = screen.cursor
        if cursor.y == y:
            self._painted_cursor_row = y
        if (
            self.has_focus
            and self._cursor_visible
            and not cursor.hidden
            and cursor.y == y
            and 0 <= cursor.x < screen.columns
        ):
            x = cursor.x
            if not screen.buffer[y][x].data and x:
                x -= 1
            width = (
                2 if x + 1 < screen.columns and not screen.buffer[y][x + 1].data else 1
            )
            style = (
                _CURSOR_UNREVERSE_STYLE
                if screen.buffer[y][x].reverse
                else _CURSOR_STYLE
            )
            strip = _overlay_style(strip, x, x + width, style)
        selection = self.text_selection
        span = selection.get_span(y) if selection is not None else None
        if span is not None:
            start, end = span
            start = min(start, screen.columns)
            end = screen.columns if end == -1 else min(end, screen.columns)
            style = self.screen.get_component_rich_style("screen--selection")
            strip = _overlay_style(strip, start, end, style)
        return strip.apply_style(self.visual_style.rich_style)

    def render(self) -> Text:
        # Keep a text representation for inspection and accessibility. Normal
        # painting uses render_line and does not assemble this frame.
        if self._screen is None:
            return Text("(starting tmux…)")
        self._sync_lines()
        if self._frame_cache is None:
            self._frame_cache = Text("\n").join(self._line_cache)
        return self._render_cursor(
            self._frame_cache.copy(), self._screen, self._screen.columns
        )

    def get_selection(self, selection):
        """Extract using terminal cell coordinates, including wide glyphs."""
        screen = self._screen
        if screen is None:
            return None
        normalize_wide_cells(screen)
        parts = []
        for y in range(screen.lines):
            span = selection.get_span(y)
            if span is None:
                continue
            start, end = span
            end = screen.columns if end == -1 else min(end, screen.columns)
            start = min(start, screen.columns)
            if start < end and start and not screen.buffer[y][start].data:
                start -= 1
            parts.append(
                "".join(screen.buffer[y][x].data for x in range(start, end)).rstrip()
            )
        return "\n".join(parts), "\n"

    def _close(self) -> None:
        self._nav_queue.clear()
        self._input_queue_bytes = 0
        self._write_drained.set()
        if self._nav_worker is not None:
            self._nav_worker.cancel()
            self._nav_worker = None
        if self._read_resume is not None:
            self._read_resume.cancel()
            self._read_resume = None
        self._cancel_esc_coalesce()
        if self._cursor_timer is not None:
            self._cursor_timer.stop()
            self._cursor_timer = None
        self._write_buffer.clear()
        if self._master_fd is not None:
            try:
                asyncio.get_running_loop().remove_reader(self._master_fd)
            except (RuntimeError, TypeError, ValueError, OSError):
                pass
            self._unwatch_pty_writable()
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
