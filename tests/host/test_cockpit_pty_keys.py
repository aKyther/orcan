#!/usr/bin/env python3
"""Key bytes for embedded tmux — locked to keybindings.conf local binds."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KEYS_PATH = ROOT / "cockpit" / "src" / "orcan_cockpit" / "pty_keys.py"

_spec = importlib.util.spec_from_file_location("cockpit_pty_keys", KEYS_PATH)
pty_keys = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = pty_keys
_spec.loader.exec_module(pty_keys)


class KeyToBytesTests(unittest.TestCase):
    def test_alt_digit_sends_esc_prefixed_meta(self) -> None:
        self.assertEqual(pty_keys.key_to_bytes("alt+2", "2"), b"\x1b2")
        self.assertEqual(pty_keys.key_to_bytes("alt+1", "1"), b"\x1b1")

    def test_textual_option_glyph_restored_to_meta(self) -> None:
        self.assertEqual(pty_keys.key_to_bytes("trade_mark_sign", "™"), b"\x1b2")

    def test_ctrl_space_is_prefix(self) -> None:
        self.assertEqual(pty_keys.key_to_bytes("ctrl+space", " "), b"\x00")

    def test_meta_letters_local_binds(self) -> None:
        self.assertEqual(pty_keys.key_to_bytes("alt+c", None), b"\x1bc")
        self.assertEqual(pty_keys.key_to_bytes("alt+a", None), b"\x1ba")
        self.assertEqual(pty_keys.key_to_bytes("alt+q", None), b"\x1bq")

    def test_ctrl_arrows_split_panes(self) -> None:
        self.assertEqual(pty_keys.key_to_bytes("ctrl+left", None), b"\x1b[1;5D")

    def test_ctrl_shift_arrows_swap_windows(self) -> None:
        self.assertEqual(pty_keys.key_to_bytes("ctrl+shift+right", None), b"\x1b[1;6C")

    def test_alt_arrows_focus_pane_legacy_meta(self) -> None:
        self.assertEqual(pty_keys.key_to_bytes("alt+left", None), b"\x1b\x1b[D")
        self.assertEqual(pty_keys.key_to_bytes("alt+down", None), b"\x1b\x1b[B")

    def test_ctrl_alt_arrows_prev_next_window(self) -> None:
        self.assertEqual(pty_keys.key_to_bytes("alt+ctrl+left", None), b"\x1b[1;7D")

    def test_escape_deferred_for_coalesce(self) -> None:
        self.assertIsNone(pty_keys.key_to_bytes("escape", None))
        self.assertIsNone(pty_keys.key_to_bytes("escape", "\x1b"))


class EscCoalesceTests(unittest.TestCase):
    def test_meta_arrows_focus_pane_legacy(self) -> None:
        self.assertEqual(pty_keys.esc_follow_up_bytes("left"), b"\x1b\x1b[D")
        self.assertEqual(pty_keys.esc_follow_up_bytes("up"), b"\x1b\x1b[A")

    def test_esc_ctrl_arrow_becomes_meta_not_split(self) -> None:
        self.assertEqual(pty_keys.esc_follow_up_bytes("ctrl+left"), b"\x1b\x1b[D")

    def test_esc_ctrl_shift_arrow_swap(self) -> None:
        self.assertEqual(pty_keys.esc_follow_up_bytes("ctrl+shift+left"), b"\x1b[1;6D")

    def test_meta_letters_after_escape(self) -> None:
        self.assertEqual(pty_keys.esc_follow_up_bytes("c"), b"\x1bc")

    def test_meta_digits_after_escape(self) -> None:
        self.assertEqual(pty_keys.esc_follow_up_bytes("3"), b"\x1b3")


if __name__ == "__main__":
    unittest.main()
