#!/usr/bin/env python3
"""Smoke: propose → human accept → compile → pack contains the fact.

This is the lasting Context Assertion loop (not preview busy fixtures).
Reflection/recap only *queues* candidates; this test starts from an inbox
drop the way a successful haiku flush would.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "repository"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import compile_context as cc  # noqa: E402
from _orcan_lib_loader import load_orcan_module  # noqa: E402

# Inbox decision helper lives next to orcan-context-review.
import importlib.machinery
import importlib.util

_review_path = ROOT / "docker" / "rootfs" / "usr" / "local" / "bin" / "orcan-context-review"
load_orcan_module("context_inbox")
_loader = importlib.machinery.SourceFileLoader("orcan_context_review_smoke", str(_review_path))
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
review = importlib.util.module_from_spec(_spec)
_loader.exec_module(review)


def _init_repo(path: Path) -> None:
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


class AssertionLoopSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.data = root / "orcan-data"
        os.environ["ORCAN_DATA"] = str(self.data)
        self.addCleanup(os.environ.pop, "ORCAN_DATA", None)

        self.project = root / "projects" / "backend"
        _init_repo(self.project)

        self.meta = root / "meta" / "demo"
        self.meta.mkdir(parents=True)
        self.orcan = self.meta / ".orcan"
        self.orcan.mkdir()
        self.ws = {
            "name": "demo",
            "meta_path": str(self.meta),
            "projects": [{"name": "backend", "path": str(self.project)}],
        }

    def test_inbox_accept_compile_lands_in_context_assertions(self) -> None:
        """Human y on a session-style fact → CONTEXT-ASSERTIONS.md after compile."""
        inbox = self.orcan / "context-inbox"
        inbox.mkdir(parents=True)
        drop = inbox / f"{uuid.uuid4().hex[:12]}.json"
        fact = "The service listens on port 8000 in local preview."
        drop.write_text(
            json.dumps(
                {
                    "project_name": "backend",
                    "title": "App listen port",
                    "content": fact,
                    "kind": "fact",
                    "justification": "Seen in bind logs during the session.",
                    "applicability": {},
                    "epistemic_status": "fact",
                    "criticality": "normal",
                }
            ),
            encoding="utf-8",
        )

        # Same path as orcan-context-review [y]es on an inbox candidate.
        review.write_inbox_decision(drop, "accept")
        payload = json.loads(drop.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("decision"), "accept")

        cc.compile_workspace(self.ws)
        pack = self.meta / "CONTEXT-ASSERTIONS.md"
        self.assertTrue(pack.is_file(), "compile should write CONTEXT-ASSERTIONS.md")
        text = pack.read_text(encoding="utf-8")
        self.assertIn(fact, text)
        self.assertIn("App listen port", text)


if __name__ == "__main__":
    unittest.main()
