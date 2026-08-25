#!/usr/bin/env python3
"""Unit tests for orcan.automation and context_model_check."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "docker" / "rootfs" / "usr" / "local" / "lib"))

from orcan import automation as auto  # noqa: E402
from orcan import context_model_check as mc  # noqa: E402


class AutomationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data = Path(self._tmp.name)
        self.env = mock.patch.dict(os.environ, {"ORCAN_DATA": str(self.data)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_default_enabled_not_paused(self) -> None:
        self.assertTrue(auto.is_enabled())
        self.assertFalse(auto.is_paused())
        self.assertTrue(auto.is_active())
        self.assertIn("running", auto.status_line())

    def test_pause_and_enable_independent(self) -> None:
        auto.set_enabled(False)
        self.assertFalse(auto.is_active())
        self.assertIn("off", auto.status_lines()[0])
        auto.set_enabled(True)
        auto.set_paused(True)
        self.assertFalse(auto.is_active())
        self.assertIn("paused", auto.status_lines()[0])

    def test_toggle_enabled_clears_pause(self) -> None:
        auto.set_paused(True)
        auto.set_enabled(False)
        state = auto.toggle_enabled()
        self.assertTrue(state["enabled"])
        self.assertFalse(state["paused"])

    def test_toggle_pause_noop_when_disabled(self) -> None:
        auto.set_enabled(False)
        before = auto.load_automation()
        auto.toggle_paused()
        self.assertEqual(auto.load_automation(), before)

    def test_refresh_model_check_persists(self) -> None:
        with mock.patch.object(mc, "check_recap_model", return_value={"ok": True, "detail": "ok", "model": "haiku", "checked_at": "t"}):
            result = auto.refresh_model_check(force=True)
        self.assertTrue(result["ok"])
        stored = auto.load_automation().get("model_check")
        self.assertIsInstance(stored, dict)
        self.assertTrue(stored.get("ok"))


class ModelCheckTests(unittest.TestCase):
    def test_missing_claude(self) -> None:
        with mock.patch.object(mc.shutil, "which", return_value=None):
            result = mc.check_recap_model(probe=False)
        self.assertFalse(result["ok"])
        self.assertIn("PATH", result["detail"])


if __name__ == "__main__":
    unittest.main()
