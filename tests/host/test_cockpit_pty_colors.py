#!/usr/bin/env python3
"""Color mapping for the embedded tmux PTY renderer."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COLORS_PATH = ROOT / "cockpit" / "src" / "orcan_cockpit" / "pty_colors.py"

_spec = importlib.util.spec_from_file_location("cockpit_pty_colors", COLORS_PATH)
pty_colors = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = pty_colors
_spec.loader.exec_module(pty_colors)


class PyteColorMappingTests(unittest.TestCase):
    def test_brown_maps_to_yellow(self) -> None:
        self.assertEqual(pty_colors.pyte_color_to_rich("brown"), "yellow")

    def test_bright_aliases_map_to_rich_names(self) -> None:
        self.assertEqual(pty_colors.pyte_color_to_rich("brightred"), "bright_red")
        self.assertEqual(pty_colors.pyte_color_to_rich("brightbrown"), "bright_yellow")

    def test_unknown_names_return_none(self) -> None:
        for name in ("norange", "grey", "lightgray", "default", ""):
            self.assertIsNone(pty_colors.pyte_color_to_rich(name), name)

    def test_hex_palette_values_get_hash_prefix(self) -> None:
        self.assertEqual(pty_colors.pyte_color_to_rich("0d1520"), "#0d1520")


if __name__ == "__main__":
    unittest.main()
