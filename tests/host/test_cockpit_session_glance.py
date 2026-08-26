#!/usr/bin/env python3
"""Host tests for session_glance formatting (stdlib + mocked tmux)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
GLANCE_PATH = ROOT / "cockpit" / "src" / "orcan_cockpit" / "session_glance.py"

_spec = importlib.util.spec_from_file_location("cockpit_session_glance", GLANCE_PATH)
glance = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = glance
_spec.loader.exec_module(glance)


class PaneCommandsTests(unittest.TestCase):
    def test_parses_unique_commands(self) -> None:
        with mock.patch.object(
            glance.subprocess,
            "check_output",
            return_value="zsh\nclaude\nzsh\nagent\n",
        ) as check_output:
            self.assertEqual(glance.pane_commands("ws"), ["zsh", "claude", "agent"])
        check_output.assert_called_once()
        args = check_output.call_args
        self.assertEqual(
            args.args[0],
            [
                "tmux",
                "list-panes",
                "-t",
                "=ws:",
                "-F",
                "#{pane_current_command}",
            ],
        )

    def test_limits_output_to_three_unique_commands(self) -> None:
        with mock.patch.object(
            glance.subprocess,
            "check_output",
            return_value="one\ntwo\nthree\nfour\n",
        ):
            self.assertEqual(glance.pane_commands("ws"), ["one", "two", "three"])

    def test_tmux_failure_is_empty(self) -> None:
        with mock.patch.object(
            glance.subprocess,
            "check_output",
            side_effect=subprocess.CalledProcessError(1, ["tmux"]),
        ):
            self.assertEqual(glance.pane_commands("missing"), [])

    def test_tmux_timeout_is_empty(self) -> None:
        with mock.patch.object(
            glance.subprocess,
            "check_output",
            side_effect=subprocess.TimeoutExpired(["tmux"], 2),
        ):
            self.assertEqual(glance.pane_commands("slow"), [])


class LinkedWorktreeCountTests(unittest.TestCase):
    def test_counts_git_file_worktrees(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wt = root / "feature"
            wt.mkdir()
            (wt / ".git").write_text("gitdir: /somewhere\n", encoding="utf-8")
            main = root / "main"
            main.mkdir()
            (main / ".git").mkdir()
            projects = [
                {"name": "a", "path": str(wt)},
                {"name": "b", "path": str(main)},
                {"name": "c", "path": str(root / "missing")},
            ]
            self.assertEqual(glance.linked_worktree_count(projects), 1)

    def test_empty_projects(self) -> None:
        self.assertEqual(glance.linked_worktree_count(None), 0)
        self.assertEqual(glance.linked_worktree_count([]), 0)


class SessionActivityLineTests(unittest.TestCase):
    def test_recent_is_active(self) -> None:
        now = 1_000_000.0
        with mock.patch.object(
            glance.subprocess, "check_output", return_value=str(int(now - 30))
        ):
            self.assertEqual(glance.session_activity_line("ws", now=now), "active")

    def test_old_is_idle_with_age(self) -> None:
        now = 1_000_000.0
        with mock.patch.object(
            glance.subprocess, "check_output", return_value=str(int(now - 7200))
        ):
            self.assertEqual(glance.session_activity_line("ws", now=now), "idle 2h")

    def test_tmux_failure_empty(self) -> None:
        with mock.patch.object(
            glance.subprocess,
            "check_output",
            side_effect=subprocess.CalledProcessError(1, ["tmux"]),
        ):
            self.assertEqual(glance.session_activity_line("ws"), "")


class BriefActivityLineTests(unittest.TestCase):
    def test_brief_age(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brief = root / ".orcan" / "session-brief.md"
            brief.parent.mkdir(parents=True)
            brief.write_text("# handoff\n", encoding="utf-8")
            now = time.time()
            os.utime(brief, (now - 7200, now - 7200))
            self.assertEqual(glance.brief_activity_line(root, now=now), "brief 2h")

    def test_missing_brief(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(glance.brief_activity_line(Path(tmp)), "")


class GlanceLinesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        inbox = self.root / ".orcan" / "context-inbox"
        inbox.mkdir(parents=True)
        drop = inbox / "a.json"
        drop.write_text(
            json.dumps(
                {
                    "project_name": "orcan",
                    "title": "T",
                    "content": "C",
                    "justification": "J",
                }
            ),
            encoding="utf-8",
        )
        now = time.time()
        os.utime(drop, (now - 7200, now - 7200))
        self.now = now

    def test_pending_includes_age(self) -> None:
        with mock.patch.object(glance, "pane_commands", return_value=[]), mock.patch.object(
            glance, "session_activity_line", return_value=""
        ), mock.patch.object(glance, "reflection_status", return_value="reflection: (no sessions yet)"):
            lines = glance.glance_lines("ws", self.root, live=False, now=self.now)
        self.assertTrue(any(line.startswith("1 pending · 2h") for line in lines))

    def test_pending_and_panes(self) -> None:
        with mock.patch.object(glance, "pane_commands", return_value=["zsh", "claude"]), mock.patch.object(
            glance, "session_activity_line", return_value="active"
        ):
            lines = glance.glance_lines("ws", self.root, live=True, now=self.now)
        self.assertTrue(any("pending" in line for line in lines))
        self.assertTrue(any(line.startswith("panes:") for line in lines))
        self.assertLessEqual(len(lines), 3)

    def test_worktrees_and_idle_on_visibility_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wt = Path(tmp) / "wt"
            wt.mkdir()
            (wt / ".git").write_text("gitdir: x\n", encoding="utf-8")
            projects = [{"name": "p", "path": str(wt)}]
            with mock.patch.object(glance, "pane_commands", return_value=[]), mock.patch.object(
                glance, "session_activity_line", return_value="idle 40m"
            ), mock.patch.object(glance, "pending_summary", return_value={"count": 0}):
                lines = glance.glance_lines(
                    "ws", self.root, live=True, projects=projects, now=self.now
                )
        self.assertIn("1 wt · idle 40m", lines)

    def test_not_live_uses_brief_not_tmux_idle(self) -> None:
        brief = self.root / ".orcan" / "session-brief.md"
        brief.write_text("x", encoding="utf-8")
        os.utime(brief, (self.now - 3600, self.now - 3600))
        with mock.patch.object(glance, "pane_commands") as panes, mock.patch.object(
            glance, "session_activity_line"
        ) as activity:
            lines = glance.glance_lines("ws", self.root, live=False, now=self.now)
        panes.assert_not_called()
        activity.assert_not_called()
        self.assertTrue(any("brief 1h" in line for line in lines))

    def test_not_live_skips_panes(self) -> None:
        with mock.patch.object(glance, "pane_commands") as panes, mock.patch.object(
            glance, "session_activity_line", return_value=""
        ):
            lines = glance.glance_lines("ws", self.root, live=False, now=self.now)
        panes.assert_not_called()
        self.assertTrue(any("pending" in line for line in lines))

    def test_empty_or_non_live_workspace_has_no_pane_line(self) -> None:
        with mock.patch.object(glance, "pane_commands") as panes:
            self.assertEqual(glance.glance_lines(None, None, live=False), [])
            self.assertEqual(glance.glance_lines("ws", None, live=False), [])
        panes.assert_not_called()

    def test_glance_never_exceeds_three_lines(self) -> None:
        with mock.patch.object(
            glance, "pending_summary", return_value={"count": 2, "oldest_mtime": self.now - 60}
        ), mock.patch.object(
            glance, "_visibility_line", return_value="1 wt · active"
        ), mock.patch.object(glance, "pane_commands", return_value=["one", "two", "three"]):
            lines = glance.glance_lines("ws", self.root, live=True, now=self.now)
        self.assertEqual(len(lines), 3)

    def test_format_glance_empty_hint(self) -> None:
        text = glance.format_glance([])
        self.assertIn("Enter to attach", text)

    def test_format_glance_escapes_markup_in_external_text(self) -> None:
        text = glance.format_glance(["review [urgent]"])
        self.assertIn(r"review \[urgent]", text)


if __name__ == "__main__":
    unittest.main()
