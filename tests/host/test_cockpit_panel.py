#!/usr/bin/env python3
"""Unit tests for the cockpit's pure, framework-free logic: pending-summary
computation (orcan.context_inbox, vendored/stdlib-only) and action command
construction (orcan_cockpit.actions, from the cockpit/ uv project).
Deliberately does NOT import orcan_cockpit.app / picker / pty_terminal /
panel — those need Textual/pyte/watchfiles, installed only into the
container's isolated /opt/orcan-cockpit/venv via `uv sync` (see
cockpit/pyproject.toml + Dockerfile), not on the host test runner.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _orcan_lib_loader import load_orcan_module  # noqa: E402

context_inbox = load_orcan_module("context_inbox")

ROOT = Path(__file__).resolve().parents[2]
ACTIONS_PATH = ROOT / "cockpit" / "src" / "orcan_cockpit" / "actions.py"

# actions.py is stdlib-only (no intra-package `orcan.*`/`orcan_cockpit.*`
# imports), so it can be loaded directly by file path — no need to install
# the orcan-cockpit uv project (Textual/pyte/etc.) just to test this module,
# and no need for the orcan-package-stub machinery _orcan_lib_loader
# provides for context_inbox above.
_spec = importlib.util.spec_from_file_location("cockpit_actions", ACTIONS_PATH)
actions = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(actions)


class PendingSummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.workspace_root = Path(self._tmp.name)
        self.inbox = self.workspace_root / ".orcan" / "context-inbox"
        self.inbox.mkdir(parents=True)

    def _drop(self, name: str, payload: dict) -> None:
        (self.inbox / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_empty_workspace_has_zero_pending(self) -> None:
        summary = context_inbox.pending_summary(self.workspace_root)
        self.assertEqual(summary["count"], 0)
        self.assertIsNone(summary["oldest_mtime"])

    def test_counts_undecided_inbox_drops(self) -> None:
        self._drop("a1", {"project_name": "orcan", "title": "T", "content": "C", "justification": "J"})
        self._drop("a2", {"project_name": "orcan", "title": "T2", "content": "C2", "justification": "J"})
        summary = context_inbox.pending_summary(self.workspace_root)
        self.assertEqual(summary["count"], 2)
        self.assertIsNotNone(summary["oldest_mtime"])

    def test_ignores_already_decided_and_flag_drops(self) -> None:
        self._drop(
            "decided",
            {"project_name": "orcan", "title": "T", "content": "C", "justification": "J", "decision": "accept"},
        )
        self._drop("flag", {"project_name": "orcan", "flag_existing_id": "abc", "reason": "stale"})
        summary = context_inbox.pending_summary(self.workspace_root)
        self.assertEqual(summary["count"], 0)

    def test_adds_review_queue_candidates_and_reconsider(self) -> None:
        queue = {
            "candidates": [{"id": "cand1", "project_name": "orcan", "title": "T", "content": "C"}],
            "reconsider": [{"id": "acc1", "project_name": "orcan", "title": "T"}],
        }
        (self.workspace_root / ".orcan" / "context-review-queue.json").write_text(
            json.dumps(queue), encoding="utf-8"
        )
        summary = context_inbox.pending_summary(self.workspace_root)
        self.assertEqual(summary["count"], 2)

    def test_oldest_mtime_is_the_minimum_across_sources(self) -> None:
        import os

        self._drop("newer", {"project_name": "orcan", "title": "T", "content": "C", "justification": "J"})
        now = time.time()
        os.utime(self.inbox / "newer.json", (now - 10, now - 10))
        queue_path = self.workspace_root / ".orcan" / "context-review-queue.json"
        queue_path.write_text(
            json.dumps({"candidates": [{"id": "c", "project_name": "orcan", "title": "T"}], "reconsider": []}),
            encoding="utf-8",
        )
        os.utime(queue_path, (now - 500, now - 500))
        summary = context_inbox.pending_summary(self.workspace_root)
        self.assertAlmostEqual(summary["oldest_mtime"], now - 500, delta=1)


class FormatPendingAgeTests(unittest.TestCase):
    def test_none_is_empty_string(self) -> None:
        self.assertEqual(context_inbox.format_pending_age(None), "")

    def test_minutes(self) -> None:
        now = 1_000_000.0
        self.assertEqual(context_inbox.format_pending_age(now - 300, now=now), "5m")

    def test_hours(self) -> None:
        now = 1_000_000.0
        self.assertEqual(context_inbox.format_pending_age(now - 7200, now=now), "2h")

    def test_days(self) -> None:
        now = 1_000_000.0
        self.assertEqual(context_inbox.format_pending_age(now - 2 * 86400, now=now), "2d")


class ReflectionStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.workspace_root = Path(self._tmp.name)

    def test_missing_state_file(self) -> None:
        self.assertIn("no sessions yet", context_inbox.reflection_status(self.workspace_root))

    def test_ok_when_no_errors_recorded(self) -> None:
        state_dir = self.workspace_root / ".orcan"
        state_dir.mkdir(parents=True)
        (state_dir / "reflection-state.json").write_text(
            json.dumps({"sess1": {"turns_since_reflection": 3, "last_transcript_line": 10}}),
            encoding="utf-8",
        )
        self.assertEqual(context_inbox.reflection_status(self.workspace_root), "reflection: ok")

    def test_surfaces_last_error(self) -> None:
        state_dir = self.workspace_root / ".orcan"
        state_dir.mkdir(parents=True)
        (state_dir / "reflection-state.json").write_text(
            json.dumps({"sess1": {"last_error": "model call failed: boom", "last_error_at": "2026-01-01T00:00:00"}}),
            encoding="utf-8",
        )
        status = context_inbox.reflection_status(self.workspace_root)
        self.assertIn("⚠", status)
        self.assertIn("boom", status)

    def test_malformed_state_file_does_not_raise(self) -> None:
        state_dir = self.workspace_root / ".orcan"
        state_dir.mkdir(parents=True)
        (state_dir / "reflection-state.json").write_text("{not json", encoding="utf-8")
        self.assertIn("unreadable", context_inbox.reflection_status(self.workspace_root))


class ContextReviewPopupCommandTests(unittest.TestCase):
    def test_targets_the_given_session(self) -> None:
        cmd = actions.context_review_popup_command("my-session")
        self.assertIn("tmux", cmd)
        self.assertIn("display-popup", cmd)
        self.assertIn("=my-session", cmd)

    def test_runs_orcan_context_review(self) -> None:
        cmd = actions.context_review_popup_command("s")
        self.assertTrue(any("orcan-context-review" in part for part in cmd))

    def test_run_context_review_popup_never_touches_stdin(self) -> None:
        from unittest import mock

        with mock.patch.object(actions.subprocess, "run") as run:
            actions.run_context_review_popup("s")
        run.assert_called_once()
        # Popups own their own controlling terminal — no stdin plumbing needed
        # (unlike the model-call subprocess calls elsewhere, which explicitly
        # pass stdin=DEVNULL); confirm no unexpected stdin kwarg was added.
        self.assertNotIn("stdin", run.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
