#!/usr/bin/env python3
"""Unit tests for the cockpit's status-bar logic (status.py) — pure/stdlib
only, no Textual import, loaded directly by file path exactly like
actions.py (see test_cockpit_panel.py's comment on why that's safe here)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATUS_PATH = ROOT / "cockpit" / "src" / "orcan_cockpit" / "status.py"

_spec = importlib.util.spec_from_file_location("cockpit_status", STATUS_PATH)
status = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(status)


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class GitBranchTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        _run_git(["init", "-b", "main"], self.repo)
        _run_git(["config", "user.email", "t@example.com"], self.repo)
        _run_git(["config", "user.name", "t"], self.repo)
        (self.repo / "README").write_text("x\n", encoding="utf-8")
        _run_git(["add", "README"], self.repo)
        _run_git(["commit", "-m", "init"], self.repo)

    def test_reports_current_branch(self) -> None:
        self.assertEqual(status.git_branch(str(self.repo)), "main")

    def test_detached_head_falls_back_to_short_sha(self) -> None:
        _run_git(["checkout", "--detach"], self.repo)
        branch = status.git_branch(str(self.repo))
        self.assertNotEqual(branch, "HEAD")
        self.assertTrue(1 <= len(branch) <= 12)

    def test_non_git_directory_is_empty_string(self) -> None:
        with tempfile.TemporaryDirectory() as not_a_repo:
            self.assertEqual(status.git_branch(not_a_repo), "")


@unittest.skipUnless(sys.platform == "linux", "/proc is Linux-specific")
class ProcReadsTests(unittest.TestCase):
    def test_read_loadavg_returns_a_number_string(self) -> None:
        value = status.read_loadavg()
        self.assertIsNotNone(value)
        float(value)  # does not raise

    def test_read_mem_percent_returns_a_percentage(self) -> None:
        value = status.read_mem_percent()
        self.assertIsNotNone(value)
        self.assertTrue(value.endswith("%"))
        percent = int(value[:-1])
        self.assertTrue(0 <= percent <= 100)


class FormatStatusLineTests(unittest.TestCase):
    """CPU/RAM/clock moved to the top bar (format_top_bar_right, below) —
    the bottom bar is workspace-identity only now."""

    def test_full_tier_includes_every_field(self) -> None:
        line = status.format_status_line(
            tier="full", workspace="orcan", branch="main", session="orcan-dev", pending=3,
        )
        for expected in ("orcan", "main", "orcan-dev", "3"):
            self.assertIn(expected, line)

    def test_compact_tier_drops_branch_and_session(self) -> None:
        line = status.format_status_line(
            tier="compact", workspace="orcan", branch="main", session="orcan-dev", pending=3,
        )
        self.assertIn("orcan", line)
        self.assertIn("3", line)
        self.assertNotIn("main", line)
        self.assertNotIn("orcan-dev", line)

    def test_minimal_tier_is_workspace_and_pending_only(self) -> None:
        line = status.format_status_line(
            tier="minimal", workspace="orcan", branch="main", session="orcan-dev", pending=3,
        )
        self.assertIn("orcan", line)
        self.assertIn("3", line)
        for unexpected in ("main", "orcan-dev"):
            self.assertNotIn(unexpected, line)

    def test_missing_workspace_has_a_placeholder(self) -> None:
        line = status.format_status_line(
            tier="full", workspace=None, branch="", session=None, pending=0,
        )
        self.assertIn("(no workspace)", line)


class FormatTopBarRightTests(unittest.TestCase):
    def test_includes_all_present_fields(self) -> None:
        line = status.format_top_bar_right(cpu="0.4", mem="52%", clock="14:05")
        for expected in ("0.4", "52%", "14:05"):
            self.assertIn(expected, line)

    def test_omits_missing_cpu_or_mem_but_keeps_clock(self) -> None:
        line = status.format_top_bar_right(cpu=None, mem=None, clock="14:05")
        self.assertIn("14:05", line)
        self.assertNotIn("None", line)


class NowHhmmTests(unittest.TestCase):
    def test_returns_hh_mm_format(self) -> None:
        value = status.now_hhmm()
        self.assertRegex(value, r"^\d{2}:\d{2}$")


class TierForWidthTests(unittest.TestCase):
    def test_boundaries(self) -> None:
        self.assertEqual(status.tier_for_width(200), "full")
        self.assertEqual(status.tier_for_width(120), "full")
        self.assertEqual(status.tier_for_width(119), "compact")
        self.assertEqual(status.tier_for_width(90), "compact")
        self.assertEqual(status.tier_for_width(89), "minimal")
        self.assertEqual(status.tier_for_width(40), "minimal")


if __name__ == "__main__":
    unittest.main()
