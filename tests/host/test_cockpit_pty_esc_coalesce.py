#!/usr/bin/env python3
"""ESC coalesce in embedded tmux — bare Esc must reach the PTY."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
PTY_TERMINAL_PATH = ROOT / "cockpit" / "src" / "orcan_cockpit" / "pty_terminal.py"


def _load_pty_terminal():
    spec = importlib.util.spec_from_file_location(
        "cockpit_pty_terminal", PTY_TERMINAL_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


try:
    pty_terminal = _load_pty_terminal()
    _PTY_IMPORT_ERROR: str | None = None
except ModuleNotFoundError as exc:
    # Host suite intentionally has no Textual/pyte dependency; the real
    # cockpit image exercises this module through the Docker smoke tests.
    pty_terminal = None
    _PTY_IMPORT_ERROR = str(exc)


@unittest.skipIf(
    pty_terminal is None, "cockpit dependencies unavailable: " + str(_PTY_IMPORT_ERROR)
)
class EscCoalesceFlushTests(unittest.TestCase):
    def _terminal(self) -> pty_terminal.PtyTerminal:
        term = pty_terminal.PtyTerminal(["true"], session="dev")
        term._master_fd = 1
        term._write_pty = MagicMock()
        term.set_timer = MagicMock(return_value=MagicMock())
        return term

    def test_flush_reschedules_when_timer_fires_early(self) -> None:
        term = self._terminal()
        term._esc_coalesce_until = time.monotonic() + 0.01
        term._flush_esc_coalesce()
        term._write_pty.assert_not_called()
        term.set_timer.assert_called_once()
        delay = term.set_timer.call_args[0][0]
        self.assertGreater(delay, 0)
        self.assertLessEqual(delay, 0.01)

    def test_flush_writes_esc_when_window_expired(self) -> None:
        term = self._terminal()
        term._esc_coalesce_until = time.monotonic() - 0.001
        term._flush_esc_coalesce()
        term._write_pty.assert_called_once_with(b"\x1b")
        self.assertIsNone(term._esc_coalesce_until)

    def test_flush_if_pending_at_key_boundary(self) -> None:
        term = self._terminal()
        term._esc_coalesce_until = time.monotonic() - 0.001
        term._flush_esc_if_pending()
        term._write_pty.assert_called_once_with(b"\x1b")

    def test_start_esc_coalesce_uses_set_timer_not_call_later(self) -> None:
        term = self._terminal()
        term._start_esc_coalesce()
        term.set_timer.assert_called_once()
        callback = term.set_timer.call_args[0][1]
        self.assertEqual(callback, term._flush_esc_coalesce)

    def test_close_cancels_pending_esc_timer(self) -> None:
        term = self._terminal()
        timer = MagicMock()
        term._esc_coalesce_timer = timer
        term._esc_coalesce_until = 1.0
        term._close()
        timer.stop.assert_called_once()
        self.assertIsNone(term._esc_coalesce_until)
        self.assertIsNone(term._esc_coalesce_timer)

    def test_large_pty_write_is_not_truncated_after_partial_writes(self) -> None:
        term = self._terminal()
        term._write_pty = pty_terminal.PtyTerminal._write_pty.__get__(term)
        payload = b"x" * 100_000
        chunks: list[bytes] = []

        def partial_write(_fd: int, data: bytes) -> int:
            chunk = bytes(data[:4096])
            chunks.append(chunk)
            return len(chunk)

        with patch.object(pty_terminal.os, "write", side_effect=partial_write):
            term._write_pty(payload)

        self.assertEqual(b"".join(chunks), payload)
        self.assertEqual(term._write_buffer, b"")

    def test_full_pty_defers_remaining_input_until_writable(self) -> None:
        term = self._terminal()
        term._write_pty = pty_terminal.PtyTerminal._write_pty.__get__(term)
        loop = MagicMock()
        with (
            patch.object(pty_terminal.asyncio, "get_running_loop", return_value=loop),
            patch.object(
                pty_terminal.os, "write", side_effect=[2, BlockingIOError(), 3]
            ),
        ):
            term._write_pty(b"hello")
            self.assertEqual(term._write_buffer, b"llo")
            loop.add_writer.assert_called_once_with(1, term._flush_pty_write)
            term._flush_pty_write()

        self.assertEqual(term._write_buffer, b"")
        loop.remove_writer.assert_called_once_with(1)

    def test_output_flood_yields_after_one_read_budget(self) -> None:
        term = self._terminal()
        term._stream = object()
        term._screen = MagicMock()
        term._ready = True
        term.refresh = MagicMock()
        loop = MagicMock()
        chunk = b"x" * 16384

        with (
            patch.object(pty_terminal.asyncio, "get_running_loop", return_value=loop),
            patch.object(pty_terminal.os, "read", side_effect=[chunk] * 16) as read,
            patch.object(pty_terminal, "feed_with_osc8"),
            patch.object(pty_terminal.time, "monotonic", return_value=0),
        ):
            term._on_readable()

        self.assertEqual(read.call_count, 16)
        loop.call_soon.assert_not_called()
        loop.remove_reader.assert_called_once_with(1)
        loop.call_later.assert_called_once_with(1 / 120, term._resume_pty_read)

    def test_output_flood_also_yields_when_time_budget_expires(self) -> None:
        term = self._terminal()
        term._stream = object()
        term._screen = MagicMock()
        term._ready = True
        term.refresh = MagicMock()
        loop = MagicMock()
        with (
            patch.object(pty_terminal.asyncio, "get_running_loop", return_value=loop),
            patch.object(pty_terminal.os, "read", return_value=b"x" * 16384) as read,
            patch.object(pty_terminal, "feed_with_osc8"),
            patch.object(pty_terminal.time, "monotonic", side_effect=[0, 0.02]),
        ):
            term._on_readable()
        self.assertEqual(read.call_count, 1)
        loop.call_soon.assert_not_called()
        loop.remove_reader.assert_called_once_with(1)
        loop.call_later.assert_called_once_with(1 / 120, term._resume_pty_read)

    def test_drained_pty_keeps_immediate_reader(self) -> None:
        term = self._terminal()
        term._stream = object()
        term._ready = True
        term.refresh = MagicMock()
        loop = MagicMock()
        with (
            patch.object(pty_terminal.asyncio, "get_running_loop", return_value=loop),
            patch.object(
                pty_terminal.os, "read", side_effect=[b"ok", BlockingIOError()]
            ),
            patch.object(pty_terminal, "feed_with_osc8"),
        ):
            term._on_readable()
        loop.remove_reader.assert_not_called()
        loop.call_later.assert_not_called()

    def test_close_cancels_read_resume_and_cannot_reinstall_closed_fd(self) -> None:
        term = self._terminal()
        handle = MagicMock()
        term._read_resume = handle
        loop = MagicMock()
        with (
            patch.object(pty_terminal.asyncio, "get_running_loop", return_value=loop),
            patch.object(pty_terminal.os, "close"),
        ):
            term._close()
            term._resume_pty_read()
        handle.cancel.assert_called_once()
        loop.add_reader.assert_not_called()

    def test_large_paste_is_staged_in_a_private_file(self) -> None:
        term = self._terminal()
        payload = b"x" * pty_terminal._STAGED_PASTE_BYTES
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(pty_terminal.tempfile, "tempdir", tmp),
        ):
            path = term._stage_large_paste(payload)
            self.assertIsNotNone(path)
            assert path is not None
            self.assertEqual(Path(path).read_bytes(), payload)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_staged_paste_cleanup_removes_only_expired_files(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(pty_terminal.tempfile, "tempdir", tmp),
        ):
            expired = Path(tmp) / "orcan-paste-expired.md"
            fresh = Path(tmp) / "orcan-paste-fresh.md"
            unrelated = Path(tmp) / "keep.md"
            for path in (expired, fresh, unrelated):
                path.write_text("x", encoding="utf-8")
            old = time.time() - pty_terminal._STAGED_PASTE_MAX_AGE_S - 1
            os.utime(expired, (old, old))

            pty_terminal.PtyTerminal._purge_staged_pastes()

            self.assertFalse(expired.exists())
            self.assertTrue(fresh.exists())
            self.assertTrue(unrelated.exists())

    def test_large_paste_sends_file_instruction_not_the_payload(self) -> None:
        term = self._terminal()
        event = MagicMock(text="x" * pty_terminal._STAGED_PASTE_BYTES)
        with patch.object(
            term, "_stage_large_paste", return_value="/tmp/orcan-paste-test.md"
        ):
            term.on_paste(event)
        event.stop.assert_called_once()
        prompt = term._write_pty.call_args.args[0].decode()
        self.assertIn("/tmp/orcan-paste-test.md", prompt)
        self.assertNotIn("x" * 100, prompt)

    def test_cursor_offset_tracks_pyte_cursor_and_respects_visibility(self) -> None:
        screen = pty_terminal.pyte.Screen(8, 3)
        screen.cursor.x = 3
        screen.cursor.y = 1

        self.assertEqual(
            pty_terminal.PtyTerminal._cursor_offset(
                screen, 8, focused=True, visible=True
            ),
            12,
        )
        self.assertIsNone(
            pty_terminal.PtyTerminal._cursor_offset(
                screen, 8, focused=False, visible=True
            )
        )
        self.assertIsNone(
            pty_terminal.PtyTerminal._cursor_offset(
                screen, 8, focused=True, visible=False
            )
        )
        screen.cursor.hidden = True
        self.assertIsNone(
            pty_terminal.PtyTerminal._cursor_offset(
                screen, 8, focused=True, visible=True
            )
        )


@unittest.skipIf(pty_terminal is None, "cockpit dependencies unavailable")
class TerminalUnicodeTests(unittest.TestCase):
    def terminal(self, columns=40, lines=3):
        term = pty_terminal.PtyTerminal(["true"])
        term._screen = pty_terminal.pyte.Screen(columns, lines)
        term._stream = pty_terminal.pyte.Stream(term._screen)
        return term

    def test_utf8_survives_every_byte_boundary_in_real_read_callback(self):
        term = self.terminal()
        term._master_fd = 123
        term._ready = True
        term._schedule_refresh = MagicMock()
        payload = "zażółć 界 😀".encode()
        for byte in payload:
            with patch.object(
                pty_terminal.os, "read", side_effect=[bytes([byte]), BlockingIOError()]
            ):
                term._on_readable()
        self.assertEqual(term.render().plain.splitlines()[0].rstrip(), "zażółć 界 😀")

    def test_eof_preserves_final_output_and_flushes_incomplete_utf8(self):
        term = self.terminal()
        term._master_fd = 123
        term._ready = True
        term._schedule_refresh = MagicMock()
        with (
            patch.object(pty_terminal.os, "read", side_effect=[b"last\xe2", b""]),
            patch.object(term, "_close") as close,
        ):
            term._on_readable()
        self.assertEqual(term.render().plain.splitlines()[0].rstrip(), "last�")
        close.assert_called_once()
        term._schedule_refresh.assert_called_once()
        self.assertIsNone(term._read_resume)

    def test_wide_glyph_and_combining_mark_do_not_add_cells(self):
        term = self.terminal(columns=12)
        term._stream.feed("界e\u0301X")
        row = term._render_line(term._screen, 0, 12, None)
        self.assertTrue(row.plain.startswith("界éX"))
        from rich.cells import cell_len

        self.assertEqual(cell_len(row.plain), 12)
        self.assertEqual(
            term._cursor_offset(term._screen, 12, focused=True, visible=True), 3
        )

    def test_plain_link_after_wide_glyph_uses_cell_coordinates(self):
        term = self.terminal()
        term._stream.feed("界 https://example.com")
        from orcan_cockpit.pty_links import url_at_screen

        self.assertIsNone(url_at_screen(term._screen, 2, 0))
        self.assertEqual(url_at_screen(term._screen, 3, 0), "https://example.com")
        row = term._render_line(term._screen, 0, 40, None)
        link_spans = [span for span in row.spans if span.style.link]
        self.assertEqual(link_spans[0].start, 2)
        term._stream.feed("\r界https://example.com\x1b[K")
        self.assertIsNone(url_at_screen(term._screen, 1, 0))
        self.assertEqual(url_at_screen(term._screen, 2, 0), "https://example.com")

    def test_selection_uses_cells_and_preserves_wide_glyph(self):
        from textual.geometry import Offset
        from textual.selection import Selection

        term = self.terminal()
        term._stream.feed("界abc")
        self.assertEqual(
            term.get_selection(Selection(Offset(2, 0), Offset(5, 0)))[0], "abc"
        )
        self.assertEqual(
            term.get_selection(Selection(Offset(0, 0), Offset(2, 0)))[0], "界"
        )


@unittest.skipIf(pty_terminal is None, "cockpit dependencies unavailable")
class TerminalRowRenderingTests(unittest.IsolatedAsyncioTestCase):
    async def test_dirty_rows_cursor_selection_and_resize(self):
        from textual.app import App, ComposeResult
        from textual.geometry import Offset
        from textual.selection import Selection

        class Terminal(pty_terminal.PtyTerminal):
            def on_mount(self, event):
                event.prevent_default()
                self._screen = pty_terminal.pyte.Screen(20, 3)
                self._stream = pty_terminal.pyte.Stream(self._screen)

        class Harness(App):
            def compose(self) -> ComposeResult:
                yield Terminal(["true"])

        app = Harness()
        async with app.run_test(size=(20, 3)) as pilot:
            term = app.query_one(Terminal)
            term.focus()
            term._stream.feed("界abc\r\nsecond")
            term._schedule_refresh()
            await pilot.pause()
            self.assertEqual(term.render_line(0).cell_length, 20)
            self.assertIsNone(term._frame_cache)
            unchanged = term._strip_cache[0]
            with patch.object(term, "_render_line", wraps=term._render_line) as build:
                term._stream.feed("!")
                term._schedule_refresh()
                await pilot.pause()
                self.assertEqual([call.args[1] for call in build.call_args_list], [1])
                self.assertIs(term._strip_cache[0], unchanged)
                build.reset_mock()
                term._toggle_cursor()
                await pilot.pause()
                build.assert_not_called()
            app.screen.selections = {term: Selection(Offset(2, 0), Offset(5, 0))}
            self.assertEqual(term.render_line(0).cell_length, 20)
            term._screen.resize(3, 10)
            term._schedule_refresh()
            await pilot.pause()
            self.assertEqual(term.render_line(0).cell_length, 10)
            app.screen.selections = {}
            term._stream.feed("\x1b[H\x1b[7mX\x1b[H")
            term._cursor_visible = True
            term._schedule_refresh()
            await pilot.pause()
            # The cursor must invert an already reversed cell back to normal.
            self.assertFalse(next(iter(term.render_line(0))).style.reverse)
            frame = term.render()
            self.assertFalse(frame.get_style_at_offset(app.console, 0).reverse)
            term._cursor_visible = False
            self.assertTrue(next(iter(term.render_line(0))).style.reverse)
            self.assertTrue(
                all(segment.style is not None for segment in term.render_line(4))
            )


@unittest.skipIf(pty_terminal is None, "cockpit dependencies unavailable")
class TerminalInputAndStyleTests(unittest.TestCase):
    def terminal(self):
        term = pty_terminal.PtyTerminal(["true"], session="fixture")
        Screen, Stream = pty_terminal.attach_hyperlink_screen()
        term._screen = Screen(80, 3)
        term._stream = Stream(term._screen)
        term._master_fd = 123
        term._ready = True
        term._schedule_refresh = MagicMock()
        return term

    def feed(self, term, text):
        pty_terminal.feed_with_osc8(term._stream, term._screen, text)
        term._sync_terminal_modes()

    def test_grouped_modes_survive_bytewise_real_read_callbacks_and_reset(self):
        term = self.terminal()
        for byte in b"\x1b[?1000;1006;2004h":
            with patch.object(
                pty_terminal.os, "read", side_effect=[bytes([byte]), BlockingIOError()]
            ):
                term._on_readable()
        self.assertTrue(term._mouse_tracking)
        self.assertTrue(term._mouse_sgr)
        for char in "\x1b[?1000;1006l":
            self.feed(term, char)
        self.assertFalse(term._mouse_tracking)
        self.assertFalse(term._mouse_sgr)
        self.feed(term, "\x1b[?1002h")
        self.assertTrue(term._mouse_tracking)
        self.feed(term, "\x1bc")
        self.assertFalse(term._mouse_tracking)
        self.assertNotIn(pty_terminal._BRACKETED_PASTE_MODE, term._screen.mode)

    def test_first_output_does_not_override_explicit_mouse_disable(self):
        term = self.terminal()
        term._ready = False
        term.post_message = MagicMock()
        with patch.object(
            pty_terminal.os,
            "read",
            side_effect=[b"\x1b[?1000;1006h\x1b[?1000;1006l", BlockingIOError()],
        ):
            term._on_readable()
        self.assertTrue(term._ready)
        self.assertFalse(term._mouse_tracking)
        self.assertFalse(term._mouse_sgr)

    def test_mode_bytes_in_osc_are_not_interpreted_as_terminal_modes(self):
        term = self.terminal()
        self.feed(term, "\x1b]0;title\x1b[?1006h\x07")
        self.assertFalse(term._mouse_sgr)

    def test_paste_follows_incremental_bracketed_paste_mode(self):
        term = self.terminal()
        term._write_pty = MagicMock()
        event = SimpleNamespace(text="first\nsecond", stop=MagicMock())
        term.on_paste(event)
        term._write_pty.assert_called_with(b"first\nsecond")
        for char in "\x1b[?2004h":
            self.feed(term, char)
        term.on_paste(event)
        term._write_pty.assert_called_with(b"\x1b[200~first\nsecond\x1b[201~")
        self.feed(term, "\x1b[?2004l")
        term.on_paste(event)
        term._write_pty.assert_called_with(b"first\nsecond")

    def test_staged_paste_and_staging_failure_keep_bracketing(self):
        term = self.terminal()
        term._write_pty = MagicMock()
        self.feed(term, "\x1b[?2004h")
        payload = "x" * pty_terminal._STAGED_PASTE_BYTES
        event = SimpleNamespace(text=payload, stop=MagicMock())
        with patch.object(term, "_stage_large_paste", return_value=None):
            term.on_paste(event)
        term._write_pty.assert_called_with(
            b"\x1b[200~" + payload.encode() + b"\x1b[201~"
        )
        with patch.object(
            term, "_stage_large_paste", return_value="/tmp/orcan-test.md"
        ):
            term.on_paste(event)
        sent = term._write_pty.call_args.args[0]
        self.assertTrue(sent.startswith(b"\x1b[200~"))
        self.assertTrue(sent.endswith(b"\x1b[201~"))
        self.assertIn(b"/tmp/orcan-test.md", sent)

    def test_mouse_keyboard_and_release_keep_order_after_partial_and_full_write(self):
        term = self.terminal()
        term._mouse_tracking = True
        term._mouse_sgr = True
        term._term_size = MagicMock(return_value=(24, 80))
        event = SimpleNamespace(x=4, y=2, button=1, shift=False, meta=False, ctrl=False)
        accepted = []
        writable = False
        first = True

        def write(fd, data):
            nonlocal first
            if first:
                first = False
                accepted.append(bytes(data[:2]))
                return 2
            if not writable:
                raise BlockingIOError
            accepted.append(bytes(data))
            return len(data)

        loop = MagicMock()
        with (
            patch.object(pty_terminal.os, "write", side_effect=write),
            patch.object(pty_terminal.asyncio, "get_running_loop", return_value=loop),
        ):
            term._write_mouse(event)
            term._write_pty(b"k")
            term._write_mouse(event, release=True)
            self.assertTrue(term._write_buffer)
            writable = True
            term._flush_pty_write()
        self.assertEqual(b"".join(accepted), b"\x1b[<0;5;3Mk\x1b[<0;5;3m")
        self.assertFalse(term._write_buffer)
        loop.add_writer.assert_called_once()
        loop.remove_writer.assert_called_once()

    def test_default_and_explicit_inverse_are_distinct_from_normal(self):
        for fg, bg in (("default", "default"), ("red", "default"), ("red", "blue")):
            normal = pty_terminal._char_style(
                pty_terminal.pyte.screens.Char("x", fg=fg, bg=bg)
            )
            inverse = pty_terminal._char_style(
                pty_terminal.pyte.screens.Char("x", fg=fg, bg=bg, reverse=True)
            )
            self.assertNotEqual(normal, inverse)
            self.assertTrue(inverse.reverse)
            self.assertEqual(normal.color, inverse.color)
            self.assertEqual(normal.bgcolor, inverse.bgcolor)

    def test_style_cache_is_bounded_and_reuses_recent_styles(self):
        cache = pty_terminal._cached_style
        cache.cache_clear()
        try:
            char = pty_terminal.pyte.screens.Char("x")
            for number in range(pty_terminal._STYLE_CACHE_LIMIT + 20):
                last = pty_terminal._char_style(char, f"https://example.com/{number}")
            self.assertEqual(
                cache.cache_info().currsize, pty_terminal._STYLE_CACHE_LIMIT
            )
            self.assertIs(
                last, pty_terminal._char_style(char, f"https://example.com/{number}")
            )
            before = cache.cache_info().misses
            pty_terminal._char_style(char, "https://example.com/0")
            self.assertEqual(cache.cache_info().misses, before + 1)
        finally:
            cache.cache_clear()


@unittest.skipIf(pty_terminal is None, "cockpit dependencies unavailable")
class TerminalNavigationTests(unittest.IsolatedAsyncioTestCase):
    async def test_stalled_navigation_leaves_input_and_timers_responsive_and_preserves_order(
        self,
    ):
        from textual.app import App, ComposeResult

        started, release = asyncio.Event(), asyncio.Event()
        calls = []

        async def navigate(session, key):
            calls.append(key)
            if len(calls) == 1:
                started.set()
                await release.wait()
            return True

        class Terminal(pty_terminal.PtyTerminal):
            def on_mount(self, event):
                event.prevent_default()
                self._master_fd = 123
                self._write_pty = MagicMock()
                self.focus()

            def on_resize(self, event):
                event.prevent_default()

            def _close(self):
                self._master_fd = None
                super()._close()

        class Harness(App):
            ticks = 0

            def compose(self) -> ComposeResult:
                yield Terminal(["true"], session="fixture")

            def on_mount(self):
                self.set_interval(0.01, self.tick)

            def tick(self):
                self.ticks += 1

        app = Harness()
        with patch.object(pty_terminal, "run_nav", new=AsyncMock(side_effect=navigate)):
            async with app.run_test(size=(40, 5)) as pilot:
                term = app.query_one(Terminal)
                await pilot.press("ctrl+left")
                await asyncio.wait_for(started.wait(), 1)
                before = app.ticks
                await pilot.press("ctrl+right", "a")
                await pilot.pause(0.03)
                term._write_pty.assert_called_with(b"a")
                self.assertGreater(app.ticks, before)
                self.assertEqual(calls, ["ctrl+left"])
                release.set()
                await app.workers.wait_for_complete()
                self.assertEqual(calls, ["ctrl+left", "ctrl+right"])
                self.assertFalse(term._nav_running)

    async def test_queue_capacity_failure_and_close(self):
        term = pty_terminal.PtyTerminal(["true"], session="fixture")
        term.run_worker = MagicMock()
        term.notify = MagicMock()
        for _ in range(pty_terminal._NAV_QUEUE_LIMIT + 2):
            self.assertTrue(term._queue_nav("ctrl+left"))
        self.assertEqual(len(term._nav_queue), pty_terminal._NAV_QUEUE_LIMIT)
        term.run_worker.assert_called_once()
        self.assertFalse(term._queue_nav("a"))
        with patch.object(
            pty_terminal, "run_nav", new=AsyncMock(side_effect=TimeoutError)
        ) as navigate:
            await term._drain_nav()
        navigate.assert_awaited_once()
        self.assertFalse(term._nav_queue)
        self.assertFalse(term._nav_running)
        self.assertTrue(term.notify.called)
        term._queue_nav("ctrl+right")
        worker = term._nav_worker
        term._close()
        worker.cancel.assert_called_once()
        self.assertFalse(term._nav_queue)


if __name__ == "__main__":
    unittest.main()
