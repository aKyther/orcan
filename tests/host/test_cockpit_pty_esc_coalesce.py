#!/usr/bin/env python3
"""ESC coalesce in embedded tmux — bare Esc must reach the PTY."""

from __future__ import annotations

import importlib.util
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
PTY_TERMINAL_PATH = ROOT / "cockpit" / "src" / "orcan_cockpit" / "pty_terminal.py"


def _load_pty_terminal():
    spec = importlib.util.spec_from_file_location("cockpit_pty_terminal", PTY_TERMINAL_PATH)
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


@unittest.skipIf(pty_terminal is None, "cockpit dependencies unavailable: " + str(_PTY_IMPORT_ERROR))
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
            patch.object(pty_terminal.os, "write", side_effect=[2, BlockingIOError(), 3]),
        ):
            term._write_pty(b"hello")
            self.assertEqual(term._write_buffer, b"llo")
            loop.add_writer.assert_called_once_with(1, term._flush_pty_write)
            term._flush_pty_write()

        self.assertEqual(term._write_buffer, b"")
        loop.remove_writer.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
