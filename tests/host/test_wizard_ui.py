#!/usr/bin/env python3
"""Unit tests for wizard_ui.py's shared prompt/output helpers (moved out of
config-wizard.py so config-wizard.py and settings-wizard.py can both use
them)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "repository"
sys.path.insert(0, str(SCRIPTS))

import wizard_ui as wu  # noqa: E402


class ColorGatingTests(unittest.TestCase):
    def test_paint_adds_escape_codes_when_color_on(self) -> None:
        with patch.object(wu, "_COLOR", True):
            self.assertEqual(wu._paint("31", "x"), "\033[31mx\033[0m")

    def test_paint_is_plain_text_when_color_off(self) -> None:
        with patch.object(wu, "_COLOR", False):
            self.assertEqual(wu._paint("31", "x"), "x")


class AskMenuTests(unittest.TestCase):
    def test_accepts_id_number_or_first_letter(self) -> None:
        options = [("keep", "keep it"), ("delete", "remove it")]
        with patch("builtins.input", side_effect=["delete"]):
            self.assertEqual(wu.ask_menu("", options, default="keep"), "delete")
        with patch("builtins.input", side_effect=["2"]):
            self.assertEqual(wu.ask_menu("", options, default="keep"), "delete")
        with patch("builtins.input", side_effect=["d"]):
            self.assertEqual(wu.ask_menu("", options, default="keep"), "delete")

    def test_empty_input_accepts_default(self) -> None:
        options = [("keep", "keep it"), ("delete", "remove it")]
        with patch("builtins.input", side_effect=[""]):
            self.assertEqual(wu.ask_menu("", options, default="keep"), "keep")


class SuccessIndentTests(unittest.TestCase):
    """success() must keep a caller's leading indent before the checkmark,
    not push the mark to column 0 and the indent after it."""

    def _captured(self, msg: str) -> str:
        buf = []
        with patch("builtins.print", side_effect=lambda s: buf.append(s)), patch.object(
            wu, "_COLOR", False
        ):
            wu.success(msg)
        return buf[0]

    def test_no_indent(self) -> None:
        self.assertEqual(self._captured("saved config"), "✓ saved config")

    def test_two_space_indent_preserved_before_mark(self) -> None:
        self.assertEqual(self._captured("  will mount folder /x"), "  ✓ will mount folder /x")

    def test_four_space_indent_preserved_before_mark(self) -> None:
        self.assertEqual(self._captured("    project ready"), "    ✓ project ready")


class AskYesNoTests(unittest.TestCase):
    def test_accepts_y_and_n(self) -> None:
        with patch("builtins.input", side_effect=["y"]):
            self.assertTrue(wu.ask_yes_no("ok?", default=False))
        with patch("builtins.input", side_effect=["n"]):
            self.assertFalse(wu.ask_yes_no("ok?", default=True))

    def test_empty_input_accepts_default(self) -> None:
        with patch("builtins.input", side_effect=["", ""]):
            self.assertTrue(wu.ask_yes_no("ok?", default=True))
            self.assertFalse(wu.ask_yes_no("ok?", default=False))


if __name__ == "__main__":
    unittest.main()
