"""Input/navigation ordering and terminal-cell invariants after wide edits."""

import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

try:
    from orcan_cockpit import pty_terminal as p
    from orcan_cockpit.pty_links import feed_with_osc8, url_at_screen
    from rich.cells import cell_len
    from textual.geometry import Offset
    from textual.selection import Selection
except ModuleNotFoundError:
    p = None


def terminal():
    term = p.PtyTerminal(["true"], session="fixture")
    Screen, Stream = p.attach_hyperlink_screen(
        lambda text: term._send_pty(text.encode())
    )
    term._screen = Screen(40, 3)
    term._stream = Stream(term._screen)
    term._master_fd = 123
    term.run_worker = Mock()
    term.notify = Mock()
    return term


@unittest.skipIf(p is None, "cockpit dependencies unavailable")
class OrderedInputTests(unittest.IsolatedAsyncioTestCase):
    async def test_keys_paste_and_mouse_follow_their_navigation(self):
        term = terminal()
        started, release = asyncio.Event(), asyncio.Event()
        observed = []

        async def navigate(session, key):
            if key == "ctrl+right":
                started.set()
                await release.wait()
            else:
                feed_with_osc8(term._stream, term._screen, "\x1b[?1000;1006;2004h")
                term._sync_terminal_modes()
            observed.append(("nav", key))

        term._send_pty = Mock(
            side_effect=lambda data: observed.append(("input", bytes(data)))
        )
        term._term_size = Mock(return_value=(3, 40))
        term._queue_nav("ctrl+right")
        with patch.object(p, "run_nav", new=AsyncMock(side_effect=navigate)):
            task = asyncio.create_task(term._drain_nav())
            await asyncio.wait_for(started.wait(), 1)
            term._write_pty(b"a")
            term._queue_nav("ctrl+left")
            term._write_paste(b"multi\nline")
            event = SimpleNamespace(
                x=4, y=2, button=1, shift=False, meta=False, ctrl=False
            )
            term._write_mouse(event)
            event.x = 30  # The queued mouse event must be a snapshot.
            term._write_pty(b"\r")
            self.assertEqual(observed, [])
            release.set()
            await task
        self.assertEqual(
            observed,
            [
                ("nav", "ctrl+right"),
                ("input", b"a"),
                ("nav", "ctrl+left"),
                ("input", b"\x1b[200~multi\nline\x1b[201~"),
                ("input", b"\x1b[<0;5;3M"),
                ("input", b"\r"),
            ],
        )
        self.assertEqual(term._input_queue_bytes, 0)

    async def test_navigation_waits_for_previous_backpressured_input(self):
        term = terminal()
        loop = asyncio.get_running_loop()
        term._watch_pty_writable = Mock()
        term._unwatch_pty_writable = Mock()
        observed = []
        with patch.object(p.os, "write", side_effect=BlockingIOError):
            term._write_pty(b"before")
        term._queue_nav("ctrl+right")
        navigate = AsyncMock(side_effect=lambda *args: observed.append("nav"))
        with patch.object(p, "run_nav", new=navigate):
            task = loop.create_task(term._drain_nav())
            await asyncio.sleep(0.01)
            navigate.assert_not_awaited()
            with patch.object(
                p.os,
                "write",
                side_effect=lambda fd, data: observed.append(bytes(data)) or len(data),
            ):
                term._flush_pty_write()
            await task
        self.assertEqual(observed, [b"before", "nav"])

    async def test_navigation_failure_does_not_send_input_to_old_pane(self):
        term = terminal()
        term._send_pty = Mock()
        term._queue_nav("ctrl+right")
        term._write_pty(b"must not reach old pane")
        term._write_paste(b"paste")
        with patch.object(p, "run_nav", new=AsyncMock(side_effect=TimeoutError)):
            await term._drain_nav()
        term._send_pty.assert_not_called()
        self.assertFalse(term._nav_queue)
        self.assertEqual(term._input_queue_bytes, 0)
        term.notify.assert_called_once()

    async def test_write_failure_prevents_navigation(self):
        term = terminal()
        term._unwatch_pty_writable = Mock()
        with patch.object(p.os, "write", side_effect=OSError):
            term._write_pty(b"before")
        term._queue_nav("ctrl+right")
        with patch.object(p, "run_nav", new=AsyncMock()) as navigate:
            await term._drain_nav()
        navigate.assert_not_awaited()
        term.notify.assert_called_once()

    async def test_protocol_reply_bypasses_pending_user_navigation(self):
        term = terminal()
        term._send_pty = Mock()
        term._queue_nav("ctrl+right")
        feed_with_osc8(term._stream, term._screen, "\x1b[2;3H\x1b[6n")
        term._send_pty.assert_called_once_with(b"\x1b[2;3R")
        self.assertEqual(list(term._nav_queue), [("nav", "ctrl+right")])

    async def test_queue_limits_and_escape_before_paste(self):
        term = terminal()
        term._queue_nav("ctrl+right")
        term._esc_coalesce_until = time.monotonic() + 1
        term.on_paste(SimpleNamespace(text="paste", stop=Mock()))
        self.assertEqual(
            list(term._nav_queue),
            [("nav", "ctrl+right"), ("data", bytearray(b"\x1b")), ("paste", b"paste")],
        )
        self.assertIsNone(term._esc_coalesce_until)
        with patch.object(p, "_INPUT_QUEUE_BYTES_LIMIT", 6):
            term._write_pty(b"overflow")
        self.assertEqual(term._input_queue_bytes, 6)
        term.notify.assert_called_once()


@unittest.skipIf(p is None, "cockpit dependencies unavailable")
class WideCellTests(unittest.TestCase):
    def test_partial_overwrite_erase_and_shift_keep_exact_width(self):
        cases = [
            ("界Z\rX", "X Z"),
            ("界Z\x1b[2GX", " XZ"),
            ("界Z\r\x1b[X", "  Z"),
            ("界Z\x1b[2G\x1b[X", "  Z"),
            ("界Z\x1b[2G\x1b[P", " Z"),
            ("界Z\x1b[2G\x1b[@", "   Z"),
        ]
        for sequence, prefix in cases:
            with self.subTest(sequence=sequence):
                term = terminal()
                feed_with_osc8(term._stream, term._screen, sequence)
                row = term._render_line(term._screen, 0, 40, term._screen.link_at)
                self.assertEqual(cell_len(row.plain), 40)
                self.assertTrue(row.plain.startswith(prefix), repr(row.plain))

    def test_edit_clears_orphan_href_without_moving_following_link(self):
        term = terminal()
        feed_with_osc8(
            term._stream,
            term._screen,
            "\x1b]8;;https://wide.example\x07界\x1b]8;;\x07https://next.example\rX",
        )
        self.assertIsNone(url_at_screen(term._screen, 1, 0))
        self.assertEqual(url_at_screen(term._screen, 2, 0), "https://next.example")
        self.assertEqual(
            term.get_selection(Selection(Offset(0, 0), Offset(3, 0)))[0], "X h"
        )

    def test_combining_mark_on_wide_glyph_preserves_two_cell_pair(self):
        term = terminal()
        for chunk in ("界", "\u0301", "Z"):
            feed_with_osc8(term._stream, term._screen, chunk)
        row = term._render_line(term._screen, 0, 40, None)
        self.assertEqual(cell_len(row.plain), 40)
        self.assertTrue(row.plain.startswith("界\u0301Z"))
        self.assertEqual(term._screen.buffer[0][1].data, "")

    def test_format_character_does_not_discard_remaining_output(self):
        term = terminal()
        feed_with_osc8(term._stream, term._screen, "a✈️suffix")
        row = term._render_line(term._screen, 0, 40, None)
        self.assertTrue(row.plain.startswith("a✈suffix"))
        self.assertEqual(cell_len(row.plain), 40)

    def test_wide_glyph_at_last_column_wraps_before_drawing(self):
        term = terminal()
        feed_with_osc8(term._stream, term._screen, "x" * 39 + "界Z")
        self.assertEqual(term._screen.buffer[0][39].data, " ")
        self.assertEqual(term._screen.buffer[1][0].data, "界")
        self.assertEqual(term._screen.buffer[1][1].data, "")
        self.assertEqual(term._screen.buffer[1][2].data, "Z")
        for y in range(3):
            self.assertEqual(
                cell_len(term._render_line(term._screen, y, 40, None).plain), 40
            )
