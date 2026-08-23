#!/usr/bin/env python3
"""Unit tests for scripts/repository/history.py (recent projects/workspaces)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "repository"
sys.path.insert(0, str(SCRIPTS))

import history  # noqa: E402


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--quiet", "-b", "main"], cwd=path, check=True, capture_output=True)


class RecordAndRecentTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data = Path(self._tmp.name)
        self.store = history.store_path(self.data)

    def test_first_use_creates_row_with_count_one(self) -> None:
        history.record_use(self.store, workspace="ws-a", now=100.0)
        rows = history.load(self.store)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["workspace"], "ws-a")
        self.assertEqual(rows[0]["usage_count"], 1)
        self.assertEqual(rows[0]["last_used"], 100.0)

    def test_repeated_use_bumps_count_and_last_used_without_duplicating(self) -> None:
        history.record_use(self.store, workspace="ws-a", now=100.0)
        history.record_use(self.store, workspace="ws-a", now=200.0)
        rows = history.load(self.store)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["usage_count"], 2)
        self.assertEqual(rows[0]["last_used"], 200.0)

    def test_different_workspaces_are_separate_rows(self) -> None:
        history.record_use(self.store, workspace="ws-a", now=100.0)
        history.record_use(self.store, workspace="ws-b", now=101.0)
        rows = history.load(self.store)
        self.assertEqual(len(rows), 2)

    def test_recent_sorts_newest_first_and_respects_limit(self) -> None:
        history.record_use(self.store, workspace="ws-old", now=1.0)
        history.record_use(self.store, workspace="ws-new", now=999.0)
        history.record_use(self.store, workspace="ws-mid", now=500.0)

        rows = history.recent(self.store, limit=2)

        self.assertEqual([r["workspace"] for r in rows], ["ws-new", "ws-mid"])

    def test_recent_can_filter_by_workspace(self) -> None:
        history.record_use(self.store, workspace="ws-a", worktree="wt1", now=1.0)
        history.record_use(self.store, workspace="ws-a", worktree="wt2", now=2.0)
        history.record_use(self.store, workspace="ws-b", now=3.0)

        rows = history.recent(self.store, workspace="ws-a")

        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["workspace"] == "ws-a" for r in rows))

    def test_same_repo_reused_from_different_worktrees_keys_by_canonical_project_id(self) -> None:
        main_repo = self.data / "main-repo"
        _init_repo(main_repo)

        history.record_use(self.store, workspace="ws-a", project_path=main_repo, now=1.0)
        rows = history.load(self.store)
        self.assertIsNotNone(rows[0]["project_id"])

    def test_missing_store_file_loads_as_empty(self) -> None:
        self.assertEqual(history.load(self.store), [])
        self.assertEqual(history.recent(self.store), [])


if __name__ == "__main__":
    unittest.main()
