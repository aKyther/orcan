#!/usr/bin/env python3
"""Unit tests for context_syncd (host-side --context watcher spike)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "repository"))

import context_assertions as ca  # noqa: E402
import context_syncd as syncd  # noqa: E402


def init_repo(path: Path) -> None:
    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "t"
    env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "t@example.com"
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--quiet", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True, capture_output=True)
    (path / "f").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "f"], cwd=path, check=True, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True, env=env)


class ContextSyncdTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.meta = self.home / "workspaces" / "demo"
        self.meta.mkdir(parents=True)
        self.project = self.home / "proj"
        init_repo(self.project)
        os.environ["ORCAN_DATA"] = str(self.home / "data")
        (self.home / "data").mkdir()
        runtime = {
            "workspaces": [
                {
                    "name": "demo",
                    "enabled": True,
                    "meta_path": str(self.meta),
                    "projects": [{"name": "proj", "path": str(self.project)}],
                }
            ]
        }
        mounts = self.home / "mounts"
        mounts.mkdir()
        (mounts / "runtime-config.json").write_text(json.dumps(runtime), encoding="utf-8")

    def test_fingerprint_empty_then_changes_on_drop(self) -> None:
        self.assertEqual(syncd.inbox_fingerprint(self.home), "")
        inbox = self.meta / ".orcan" / "context-inbox"
        inbox.mkdir(parents=True)
        drop = inbox / "abc.json"
        drop.write_text(
            json.dumps(
                {
                    "project_name": "proj",
                    "content": "use uv",
                    "justification": "faster",
                    "decision": "accept",
                }
            ),
            encoding="utf-8",
        )
        fp1 = syncd.inbox_fingerprint(self.home)
        self.assertTrue(fp1)
        drop.write_text(drop.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        fp2 = syncd.inbox_fingerprint(self.home)
        self.assertNotEqual(fp1, fp2)

    def test_sync_if_changed_imports_decided_drop(self) -> None:
        inbox = self.meta / ".orcan" / "context-inbox"
        inbox.mkdir(parents=True)
        (inbox / "cand.json").write_text(
            json.dumps(
                {
                    "project_name": "proj",
                    "title": "uv",
                    "content": "prefer uv over pip",
                    "justification": "project standard",
                    "kind": "fact",
                    "decision": "accept",
                }
            ),
            encoding="utf-8",
        )
        rc = syncd.sync_if_changed(self.home)
        self.assertEqual(rc, 0)
        self.assertFalse((inbox / "cand.json").exists())
        pack = self.meta / "CONTEXT-ASSERTIONS.md"
        self.assertTrue(pack.is_file())
        self.assertIn("prefer uv over pip", pack.read_text(encoding="utf-8"))
        # Second call: no changes
        with mock.patch("builtins.print") as printed:
            rc2 = syncd.sync_if_changed(self.home)
        self.assertEqual(rc2, 0)
        self.assertTrue(any("no inbox/decision changes" in str(c) for c in printed.call_args_list))

    def test_pause_skips_import_without_advancing_state(self) -> None:
        with mock.patch.object(syncd, "is_paused", return_value=True), \
            mock.patch.object(syncd, "run_compile") as compile_mock:
            rc = syncd.sync_if_changed(self.home)
        self.assertEqual(rc, 0)
        compile_mock.assert_not_called()
        self.assertFalse((self.home / "mounts" / syncd.STATE_NAME).exists())

    def test_force_bypasses_pause_for_explicit_operator_action(self) -> None:
        with mock.patch.object(syncd, "is_paused", return_value=True), \
            mock.patch.object(syncd, "run_compile", return_value=0) as compile_mock:
            rc = syncd.sync_if_changed(self.home, force=True)
        self.assertEqual(rc, 0)
        compile_mock.assert_called_once_with(self.home)
        self.assertTrue((self.home / "mounts" / syncd.STATE_NAME).is_file())


if __name__ == "__main__":
    unittest.main()
