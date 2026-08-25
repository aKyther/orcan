#!/usr/bin/env python3
"""SGR mouse encoding for the embedded tmux PTY."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
MOUSE_PATH = ROOT / "cockpit" / "src" / "orcan_cockpit" / "pty_mouse.py"

_spec = importlib.util.spec_from_file_location("cockpit_pty_mouse", MOUSE_PATH)
pty_mouse = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = pty_mouse
_spec.loader.exec_module(pty_mouse)


def _event(**kwargs: object) -> SimpleNamespace:
    defaults = {"x": 4, "y": 2, "button": 1, "shift": False, "meta": False, "ctrl": False}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class SgrMouseTests(unittest.TestCase):
    def test_scroll_down_uses_button_65(self) -> None:
        data = pty_mouse.sgr_mouse_bytes(_event(), scroll=65, rows=24, cols=80)
        self.assertEqual(data, b"\x1b[<65;5;3M")

    def test_legacy_scroll_down(self) -> None:
        data = pty_mouse.legacy_mouse_bytes(_event(), scroll=65, rows=24, cols=80)
        self.assertEqual(data, b"\x1bM" + bytes([65, 5 + 32, 3 + 32]))

    def test_mouse_bytes_respects_sgr_flag(self) -> None:
        sgr = pty_mouse.mouse_bytes(_event(), scroll=65, rows=24, cols=80, sgr=True)
        legacy = pty_mouse.mouse_bytes(_event(), scroll=65, rows=24, cols=80, sgr=False)
        self.assertEqual(sgr, b"\x1b[<65;5;3M")
        self.assertEqual(legacy, b"\x1bM" + bytes([65, 37, 35]))

    def test_parse_mouse_modes_last_wins(self) -> None:
        reset_then_on = b"\x1b[?1006l\x1b[?1000l\x1b[?1006h\x1b[?1000h"
        tracking, sgr = pty_mouse.parse_mouse_modes(reset_then_on)
        self.assertTrue(tracking)
        self.assertTrue(sgr)

    def test_parse_mouse_modes_off_after_on_in_same_chunk(self) -> None:
        # Old bug: substring `in data` saw both h and l → always ended False.
        data = b"\x1b[?1006h\x1b[?1006l"
        _tracking, sgr = pty_mouse.parse_mouse_modes(data)
        self.assertFalse(sgr)

    def test_scroll_up_uses_button_64(self) -> None:
        data = pty_mouse.sgr_mouse_bytes(_event(x=0, y=0), scroll=64, rows=24, cols=80)
        self.assertEqual(data, b"\x1b[<64;1;1M")

    def test_left_click_press_and_release(self) -> None:
        press = pty_mouse.sgr_mouse_bytes(_event(), rows=24, cols=80)
        release = pty_mouse.sgr_mouse_bytes(_event(), release=True, rows=24, cols=80)
        self.assertEqual(press, b"\x1b[<0;5;3M")
        self.assertEqual(release, b"\x1b[<32;5;3m")

    def test_coords_clamped_to_terminal_size(self) -> None:
        data = pty_mouse.sgr_mouse_bytes(_event(x=999, y=999), scroll=65, rows=10, cols=20)
        self.assertEqual(data, b"\x1b[<65;20;10M")


if __name__ == "__main__":
    unittest.main()
