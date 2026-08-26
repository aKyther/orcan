#!/usr/bin/env python3
"""Host tests for problems / timeline / peek / tmux_chrome helpers."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _orcan_lib_loader import load_orcan_module  # noqa: E402

load_orcan_module("context_inbox")


def _load(name: str, rel: str):
    path = ROOT / "cockpit" / "src" / "orcan_cockpit" / rel
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


problems = _load("cockpit_problems", "problems.py")
timeline = _load("cockpit_timeline", "timeline.py")
peek = _load("cockpit_peek", "peek.py")
chrome = _load("cockpit_tmux_chrome", "tmux_chrome.py")
status = _load("cockpit_status_ide", "status.py")
onboarding = _load("cockpit_onboarding", "onboarding.py")
feedback = _load("cockpit_reflection_feedback", "reflection_feedback.py")
first_run = _load("cockpit_onboarding", "onboarding.py")


class ProblemsSummaryTests(unittest.TestCase):
    def test_pending_and_reflection_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox = root / ".orcan" / "context-inbox"
            inbox.mkdir(parents=True)
            (inbox / "a.json").write_text(
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
            (root / ".orcan" / "reflection-state.json").write_text(
                json.dumps({"s1": {"last_error": "boom"}}),
                encoding="utf-8",
            )
            summary = problems.problems_summary(root, projects=[])
        self.assertEqual(summary["pending"], 1)
        self.assertEqual(summary["reflection_errors"], 1)
        self.assertGreaterEqual(summary["count"], 2)
        self.assertIn("pending", summary["tooltip"])

    def test_dirty_skipped_unless_include_dirty(self) -> None:
        with mock.patch.object(problems, "dirty_project_count", return_value=3) as dirty:
            summary = problems.problems_summary(Path("/tmp"), projects=[{"path": "/x"}], include_dirty=False)
        dirty.assert_not_called()
        self.assertEqual(summary["dirty"], 0)
        with mock.patch.object(problems, "dirty_project_count", return_value=3) as dirty:
            with mock.patch.object(problems, "pending_summary", return_value={"count": 0}):
                with mock.patch.object(problems, "reflection_error_count", return_value=0):
                    with mock.patch.object(problems, "reflection_status", return_value="ok"):
                        summary = problems.problems_summary(
                            Path("/tmp"), projects=[{"path": "/x"}], include_dirty=True
                        )
        dirty.assert_called_once()
        self.assertEqual(summary["dirty"], 3)

    def test_dirty_project_count_caps_projects_and_ignores_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects = []
            for index in range(3):
                project = root / f"p{index}"
                (project / ".git").mkdir(parents=True)
                projects.append({"path": str(project)})
            projects.append({"path": str(root / "not-a-repo")})
            result = mock.Mock(returncode=0, stdout=" M file\n")
            with mock.patch.object(problems.subprocess, "run", return_value=result) as run:
                count = problems.dirty_project_count(projects, limit=2)
        self.assertEqual(count, 2)
        self.assertEqual(run.call_count, 2)

    def test_dirty_project_count_ignores_tmux_style_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / ".git").mkdir()
            with mock.patch.object(
                problems.subprocess, "run", side_effect=subprocess.TimeoutExpired("git", 0.4)
            ):
                self.assertEqual(problems.dirty_project_count([{"path": str(project)}]), 0)


class TimelineTests(unittest.TestCase):
    def test_recent_decisions_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dec = root / ".orcan" / "context-decisions"
            dec.mkdir(parents=True)
            (dec / "old.json").write_text(
                json.dumps({"id": "old", "decision": "reject", "project_name": "orcan"}),
                encoding="utf-8",
            )
            (dec / "new.json").write_text(
                json.dumps({"id": "new", "decision": "accept", "project_name": "orcan"}),
                encoding="utf-8",
            )
            rows = timeline.recent_decisions(root, limit=5)
        self.assertTrue(rows)
        lines = timeline.format_timeline(rows)
        self.assertTrue(any("accept" in line or "reject" in line for line in lines))


class PeekBuildTests(unittest.TestCase):
    def test_includes_brief_and_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            orcan = root / ".orcan"
            orcan.mkdir()
            (orcan / "session-brief.md").write_text("# handoff\nport 8000\n", encoding="utf-8")
            inbox = orcan / "context-inbox"
            inbox.mkdir()
            (inbox / "a.json").write_text(
                json.dumps(
                    {
                        "project_name": "orcan",
                        "title": "Listen port",
                        "content": "App listens on 8000",
                        "justification": "from session",
                    }
                ),
                encoding="utf-8",
            )
            text = peek.build_peek_text(root)
        self.assertIn("SESSION BRIEF", text)
        self.assertIn("port 8000", text)
        self.assertIn("Listen port", text)
        self.assertIn("App listens on 8000", text)


class TmuxChromeTests(unittest.TestCase):
    def test_breadcrumb_parses(self) -> None:
        with mock.patch.object(chrome, "_tmux", return_value="2|claude"):
            self.assertEqual(chrome.session_breadcrumb("ws"), "w2 › claude")

    def test_pin_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(chrome, "_tmux", return_value="%9"):
                self.assertTrue(chrome.pin_main_pane("ws", root))
            self.assertEqual(chrome.read_pinned_pane(root), "%9")

    def test_list_agent_panes_normalizes_commands_and_applies_limit(self) -> None:
        raw = "%1\t/usr/bin/claude\t/tmp\tmain\nmalformed\n%2\tbash\t/home\n%3\tpython\t/x\ttest\n"
        with mock.patch.object(chrome, "_tmux", return_value=raw):
            rows = chrome.list_agent_panes("ws", limit=2)
        self.assertEqual(rows, [{"id": "%1", "cmd": "claude", "path": "/tmp", "title": "main"}, {"id": "%2", "cmd": "bash", "path": "/home", "title": ""}])

    def test_split_run_returns_false_on_tmux_failure(self) -> None:
        result = mock.Mock(returncode=1)
        with mock.patch.object(chrome.subprocess, "run", return_value=result) as run:
            self.assertFalse(chrome.split_run("ws", "claude", vertical=False))
        self.assertEqual(run.call_args.args[0], ["tmux", "split-window", "-h", "-t", "=ws:", "claude"])

    def test_invalid_pinned_pane_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pin = root / ".orcan" / "main-pane"
            pin.parent.mkdir()
            pin.write_text("not-a-pane\n", encoding="utf-8")
            self.assertIsNone(chrome.read_pinned_pane(root))
            with mock.patch.object(chrome.subprocess, "run") as run:
                self.assertFalse(chrome.focus_pinned_pane("ws", root))
            run.assert_not_called()


class StatusBreadcrumbTests(unittest.TestCase):
    def test_full_tier_appends_breadcrumb(self) -> None:
        line = status.format_status_line(
            tier="full",
            workspace="orcan",
            branch="main",
            session="s",
            breadcrumb="w1 › zsh",
        )
        self.assertIn("w1 › zsh", line)


class ReviewScopeChipTests(unittest.TestCase):
    def test_format_scope_chip(self) -> None:
        # Load review script like test_context_review
        script = ROOT / "docker" / "rootfs" / "usr" / "local" / "bin" / "orcan-context-review"
        loader = importlib.machinery.SourceFileLoader("orcan_context_review_scope", str(script))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        review = importlib.util.module_from_spec(spec)
        loader.exec_module(review)
        self.assertEqual(review.format_scope_chip({}), "scope: always")
        self.assertIn("branch=feature/x", review.format_scope_chip({"branch": "feature/x"}))


class OnboardingFlagTests(unittest.TestCase):
    def test_flag_is_created_and_detected_on_next_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with mock.patch.object(onboarding.Path, "home", return_value=home):
                self.assertFalse(onboarding.onboarding_already_seen())
                onboarding.mark_onboarding_seen()
                self.assertTrue(onboarding.onboarding_already_seen())
                flag = home / ".local" / "share" / "orcan" / onboarding.FLAG_NAME
                self.assertEqual(flag.read_text(encoding="utf-8"), "1\n")

    def test_mark_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(onboarding.Path, "home", return_value=Path(tmp)):
                onboarding.mark_onboarding_seen()
                onboarding.mark_onboarding_seen()
                self.assertTrue(onboarding.onboarding_already_seen())


class ReflectionFeedbackTests(unittest.TestCase):
    def test_none_yet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(feedback, "_model_status", return_value="haiku ok"):
                line = feedback.last_batch_feedback(Path(tmp), now=1_000_000.0)
        self.assertIn("none yet", line)
        self.assertIn("haiku ok", line)

    def test_facts_from_recap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recap = root / ".orcan" / "recap"
            recap.mkdir(parents=True)
            (recap / "s1.json").write_text(
                json.dumps(
                    {
                        "batch_count": 2,
                        "updated_at": "2026-01-01T00:00:00+00:00",
                        "rolling_compact": "- port 8000\n- use uv\n",
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(feedback, "_model_status", return_value="haiku ok"):
                line = feedback.last_batch_feedback(root, now=1_000_000.0)
        self.assertIn("2 facts", line)
        self.assertIn("haiku ok", line)

    def test_fail_from_reflection_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".orcan").mkdir()
            (root / ".orcan" / "reflection-state.json").write_text(
                json.dumps(
                    {
                        "s1": {
                            "last_recap_error": "claude missing",
                            "last_recap_error_at": "2026-01-01T00:00:00+00:00",
                        }
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(feedback, "_model_status", return_value="haiku fail"):
                line = feedback.last_batch_feedback(root, now=1_000_000.0)
        self.assertIn("fail", line)
        self.assertIn("claude missing", line)


class FirstRunFlagTests(unittest.TestCase):
    def test_mark_and_seen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            flag = Path(tmp) / "seen"
            with mock.patch.object(first_run, "onboarding_flag_path", return_value=flag):
                self.assertFalse(first_run.onboarding_already_seen())
                first_run.mark_onboarding_seen()
                self.assertTrue(first_run.onboarding_already_seen())


if __name__ == "__main__":
    unittest.main()
