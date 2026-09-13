"""Contract tests for the Warm Graphite / Amber Cockpit palette."""

from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "cockpit" / "src" / "orcan_cockpit" / "theme.py"
TTYD_LAUNCHER = ROOT / "docker" / "rootfs" / "usr" / "local" / "bin" / "cursor-ttyd"
spec = importlib.util.spec_from_file_location("cockpit_theme", MODULE_PATH)
assert spec and spec.loader
theme = importlib.util.module_from_spec(spec)
spec.loader.exec_module(theme)


class WarmGraphiteAmberThemeTests(unittest.TestCase):
    def test_exact_palette(self) -> None:
        self.assertEqual(
            theme.TOKENS,
            {
                "background": "#171512", "surface": "#201d19", "panel_active": "#2a251f",
                "border": "#332e28", "border_subtle": "#292420",
                "text_primary": "#f0e9e0", "text_muted": "#9a8f80", "text_disabled": "#5c554c",
                "accent": "#e8b76c", "accent_bright": "#f5c988", "accent_dim": "#a8824f",
                "running": "#8fbc6a", "error": "#e06c75", "warning": "#e5c07b",
                "idle": "#736a5e", "completed": "#7a9b8e",
            },
        )

    def test_css_normalizes_legacy_values_to_tokens(self) -> None:
        self.assertEqual(
            theme.css("background: #12101a; color: #c7b1e2;"),
            "background: #171512; color: #e8b76c;",
        )

    def test_default_ttyd_theme_uses_only_palette_tokens(self) -> None:
        launcher = TTYD_LAUNCHER.read_text(encoding="utf-8")
        match = re.search(r"^TTYD_THEME_NAVY='(?P<theme>.+)'$", launcher, re.MULTILINE)
        self.assertIsNotNone(match)
        ttyd_theme = json.loads(match.group("theme"))  # type: ignore[union-attr]

        self.assertEqual(ttyd_theme["background"], theme.BACKGROUND)
        self.assertEqual(ttyd_theme["foreground"], theme.TEXT_PRIMARY)
        self.assertEqual(ttyd_theme["cursor"], theme.ACCENT)
        self.assertTrue(set(ttyd_theme.values()).issubset(set(theme.TOKENS.values())))
