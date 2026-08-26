#!/usr/bin/env python3
"""Cockpit tmux nav chords — Ctrl/Alt+arrows focus; Ctrl+Shift+arrows split."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
NAV_PATH = ROOT / "cockpit" / "src" / "orcan_cockpit" / "pty_tmux_nav.py"
KEYBINDINGS_PATH = ROOT / "docker" / "rootfs" / "etc" / "tmux" / "keybindings.conf"

_spec = importlib.util.spec_from_file_location("cockpit_pty_tmux_nav", NAV_PATH)
nav = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = nav
_spec.loader.exec_module(nav)


class NavActionTests(unittest.TestCase):
    def test_alt_arrows_focus_pane(self) -> None:
        for direction, flag in (("left", "-L"), ("right", "-R"), ("up", "-U"), ("down", "-D")):
            self.assertEqual(nav.nav_action(f"alt+{direction}"), ("select-pane", flag))

    def test_ctrl_arrows_focus_pane(self) -> None:
        # Intentional cockpit mix: Alt often arrives as Ctrl, so both focus.
        for direction, flag in (("left", "-L"), ("right", "-R"), ("up", "-U"), ("down", "-D")):
            self.assertEqual(nav.nav_action(f"ctrl+{direction}"), ("select-pane", flag))

    def test_ctrl_shift_arrows_split_pane(self) -> None:
        self.assertEqual(nav.nav_action("ctrl+shift+left"), ("split-window", "-h", "-b"))
        self.assertEqual(nav.nav_action("ctrl+shift+right"), ("split-window", "-h"))
        self.assertEqual(nav.nav_action("ctrl+shift+up"), ("split-window", "-v", "-b"))
        self.assertEqual(nav.nav_action("ctrl+shift+down"), ("split-window", "-v"))
        self.assertEqual(nav.nav_action("shift+ctrl+left"), ("split-window", "-h", "-b"))

    def test_non_nav_keys_untouched(self) -> None:
        self.assertIsNone(nav.nav_action("ctrl+space"))
        self.assertIsNone(nav.nav_action("alt+1"))
        self.assertIsNone(nav.nav_action("alt+ctrl+left"))
        self.assertIsNone(nav.nav_action("a"))

    def test_alt_focus_still_matches_keybindings_conf(self) -> None:
        """Alt focus matches conf; Ctrl/Ctrl+Shift diverge on purpose (cockpit mix)."""
        conf = KEYBINDINGS_PATH.read_text(encoding="utf-8")
        for direction, flag in (("Left", "-L"), ("Right", "-R"), ("Up", "-U"), ("Down", "-D")):
            binding = f"bind -n M-{direction} select-pane {flag}"
            self.assertIn(binding, conf)
            self.assertEqual(
                nav.nav_action(f"alt+{direction.lower()}"),
                ("select-pane", flag),
            )
        # Conf still has Ctrl=split for raw --tmux; cockpit must NOT match that.
        self.assertIn("bind -n C-Left split-window -h -b", conf)
        self.assertNotEqual(
            nav.nav_action("ctrl+left"),
            ("split-window", "-h", "-b"),
        )


class EscFollowUpNavTests(unittest.TestCase):
    def test_bare_arrow_is_alt_arrow(self) -> None:
        self.assertEqual(nav.esc_follow_up_nav_key("left"), "alt+left")
        self.assertEqual(nav.esc_follow_up_nav_key("up"), "alt+up")

    def test_esc_ctrl_arrow_is_focus_not_split(self) -> None:
        self.assertEqual(nav.esc_follow_up_nav_key("ctrl+left"), "alt+left")
        self.assertEqual(nav.esc_follow_up_nav_key("ctrl+down"), "alt+down")

    def test_esc_ctrl_shift_not_nav_follow_up(self) -> None:
        self.assertIsNone(nav.esc_follow_up_nav_key("ctrl+shift+left"))

    def test_non_arrow_follow_ups_none(self) -> None:
        self.assertIsNone(nav.esc_follow_up_nav_key("c"))
        self.assertIsNone(nav.esc_follow_up_nav_key("3"))


class NavArgvTests(unittest.TestCase):
    def test_argv_targets_exact_session_active_pane(self) -> None:
        self.assertEqual(
            nav.nav_argv("orcan-dev", "alt+left"),
            ["tmux", "select-pane", "-L", "-t", "=orcan-dev:"],
        )
        self.assertEqual(
            nav.nav_argv("ws", "ctrl+down"),
            ["tmux", "select-pane", "-D", "-t", "=ws:"],
        )
        self.assertEqual(
            nav.nav_argv("ws", "ctrl+shift+down"),
            ["tmux", "split-window", "-v", "-t", "=ws:"],
        )

    def test_run_nav_invokes_tmux(self) -> None:
        with mock.patch.object(nav.subprocess, "run") as run:
            self.assertTrue(nav.run_nav("orcan-dev", "alt+right"))
            run.assert_called_once()
            argv = run.call_args[0][0]
            self.assertEqual(argv, ["tmux", "select-pane", "-R", "-t", "=orcan-dev:"])

    def test_run_nav_skips_non_nav(self) -> None:
        with mock.patch.object(nav.subprocess, "run") as run:
            self.assertFalse(nav.run_nav("orcan-dev", "ctrl+space"))
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
