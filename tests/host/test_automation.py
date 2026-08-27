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
        with mock.patch.object(auto, "claude_on_path", return_value=True):
            self.assertTrue(auto.is_enabled())
            self.assertFalse(auto.is_paused())
            self.assertTrue(auto.is_active())
            self.assertIn("running", auto.status_line())

    def test_pause_and_enable_independent(self) -> None:
        with mock.patch.object(auto, "claude_on_path", return_value=True):
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
        # Patch where it's *used* (automation.py does `from ... import
        # check_recap_model`, binding its own name at import time) — a
        # patch on the source module (`mc`) never intercepts that call.
        # This silently exercised the real, unmocked probe instead, which
        # only "passed" by coincidence when `claude` happened to be on
        # PATH; it fails deterministically wherever it isn't (a fresh CI
        # runner, confirmed by reproducing the CI failure locally with an
        # empty $HOME/minimal $PATH).
        with mock.patch.object(auto, "check_recap_model", return_value={"ok": True, "detail": "ok", "model": "haiku", "checked_at": "t"}):
            result = auto.refresh_model_check(force=True)
        self.assertTrue(result["ok"])
        stored = auto.load_automation().get("model_check")
        self.assertIsInstance(stored, dict)
        self.assertTrue(stored.get("ok"))

    def test_refresh_model_check_reuses_fresh_cache(self) -> None:
        cached = {
            "ok": True,
            "detail": "cached",
            "model": "haiku",
            "checked_at": auto._now_iso(),
        }
        auto.save_automation({"model_check": cached})
        with mock.patch.object(auto, "check_recap_model") as check:
            result = auto.refresh_model_check(max_age_seconds=300)
        self.assertEqual(result, cached)
        check.assert_not_called()

    def test_status_lines_explain_model_unavailable(self) -> None:
        auto.save_automation({
            "model_check": {
                "ok": False,
                "detail": "claude unavailable",
                "model": "haiku",
                "checked_at": auto._now_iso(),
            }
        })
        lines = auto.status_lines()
        self.assertTrue(any("recap model: unavailable" in line for line in lines))
        self.assertTrue(any("claude unavailable" in line for line in lines))

    def test_status_lines_report_ready_model(self) -> None:
        auto.save_automation({
            "model_check": {"ok": True, "detail": "probe ok", "model": "haiku", "checked_at": auto._now_iso()}
        })
        with mock.patch.object(auto, "claude_on_path", return_value=True):
            self.assertTrue(any("recap model: ok (haiku)" in line for line in auto.status_lines()))

    def test_sync_disables_when_claude_missing(self) -> None:
        auto.save_automation({"enabled": True, "paused": False})
        with mock.patch.object(auto, "claude_on_path", return_value=False):
            state = auto.sync_automation_to_claude_availability()
        self.assertFalse(state["enabled"])
        self.assertTrue(state.get(auto.AUTO_DISABLED_NO_CLAUDE))
        self.assertFalse(auto.is_active())

    def test_sync_restores_only_auto_disabled(self) -> None:
        auto.save_automation({
            "enabled": False,
            "paused": False,
            auto.AUTO_DISABLED_NO_CLAUDE: True,
        })
        with mock.patch.object(auto, "claude_on_path", return_value=True):
            state = auto.sync_automation_to_claude_availability()
        self.assertTrue(state["enabled"])
        self.assertNotIn(auto.AUTO_DISABLED_NO_CLAUDE, state)

    def test_human_off_not_auto_restored(self) -> None:
        auto.set_enabled(False)  # clears auto flag
        with mock.patch.object(auto, "claude_on_path", return_value=True):
            state = auto.sync_automation_to_claude_availability()
        self.assertFalse(state["enabled"])
        self.assertNotIn(auto.AUTO_DISABLED_NO_CLAUDE, state)


class AutomationDirFallbackTests(unittest.TestCase):
    """Regression: inside the container, $ORCAN_DATA is the *host* path,
    passed through unchanged for other host-side tools (doctor.sh) — not
    necessarily writable, or even related to the real (fixed) container
    bind target. A container process must fall back rather than crash.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(os.environ.pop, "ORCAN_DATA", None)

    def test_unwritable_data_root_falls_back_to_container_default(self) -> None:
        unwritable = Path(self._tmp.name) / "orcan"
        unwritable.mkdir(mode=0o500)
        self.addCleanup(os.chmod, unwritable, 0o700)  # let tempdir cleanup remove it
        os.environ["ORCAN_DATA"] = str(unwritable)
        self.assertEqual(
            auto.automation_dir(),
            Path.home() / ".local" / "share" / "orcan" / "history" / "supervisor",
        )

    def test_unwritable_history_subdir_falls_back_even_if_root_is_writable(self) -> None:
        # The root ($ORCAN_DATA itself) can be writable while a deeper
        # directory along the real target path isn't (e.g. a stale owner
        # on just "history") — must still fall back, not just check the
        # root (a first cut of this fix only checked the root and missed
        # exactly this case, confirmed against a real cockpit run).
        data = Path(self._tmp.name)
        history = data / "history"
        history.mkdir(mode=0o500)
        self.addCleanup(os.chmod, history, 0o700)
        os.environ["ORCAN_DATA"] = str(data)
        self.assertEqual(
            auto.automation_dir(),
            Path.home() / ".local" / "share" / "orcan" / "history" / "supervisor",
        )

    def test_writable_data_root_is_still_preferred(self) -> None:
        data = Path(self._tmp.name)
        os.environ["ORCAN_DATA"] = str(data)
        self.assertEqual(auto.automation_dir(), data / "history" / "supervisor")


class ModelCheckTests(unittest.TestCase):
    def test_missing_claude(self) -> None:
        with mock.patch.object(mc.shutil, "which", return_value=None):
            result = mc.check_recap_model(probe=False)
        self.assertFalse(result["ok"])
        self.assertIn("PATH", result["detail"])


if __name__ == "__main__":
    unittest.main()
