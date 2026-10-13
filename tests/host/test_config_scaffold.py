"""Regression tests for idempotent ``orcan init PATH`` scaffolding."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
SCAFFOLD = ROOT / "scripts" / "repository" / "config-scaffold.py"


class ConfigScaffoldTests(unittest.TestCase):
    def test_sibling_worktrees_keep_repository_and_branch_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "api"
            repo.mkdir()

            def git(*args):
                subprocess.run(
                    ["git", "-C", str(repo), *args],
                    check=True,
                    capture_output=True,
                    text=True,
                )

            git("init")
            git(
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.org",
                "commit",
                "--allow-empty",
                "-m",
                "Initial",
            )
            first = root / "one" / "checkout"
            second = root / "two" / "checkout"
            git("worktree", "add", "-b", "feature/login", str(first))
            git("worktree", "add", "-b", "feature-login", str(second))
            config = root / "orcan.config.json"
            for project in (repo, first, second, first, second):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCAFFOLD),
                        "--config",
                        str(config),
                        "--project-dir",
                        str(project),
                        "--workspace",
                        "acme",
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            projects = json.loads(config.read_text())["workspaces"][0]["projects"]
            self.assertEqual(
                [p["name"] for p in projects],
                ["api", "api--feature-login", "api--feature-login--2"],
            )
            self.assertEqual(
                [p["path"] for p in projects], [str(repo), str(first), str(second)]
            )

    def test_existing_project_at_same_path_is_already_connected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "api"
            project.mkdir()
            config = root / "orcan.config.json"
            args = [
                sys.executable,
                str(SCAFFOLD),
                "--config",
                str(config),
                "--project-dir",
                str(project),
                "--workspace",
                "acme",
            ]
            first = subprocess.run(args, text=True, capture_output=True, check=False)
            second = subprocess.run(args, text=True, capture_output=True, check=False)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("project already connected", second.stdout)
            cfg = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(len(cfg["workspaces"][0]["projects"]), 1)


if __name__ == "__main__":
    unittest.main()
