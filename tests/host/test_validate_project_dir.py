#!/usr/bin/env python3
"""Shell validate-project-dir.sh must match path_guards.py."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "repository" / "validate-project-dir.sh"


class ValidateProjectDirTests(unittest.TestCase):
    def _run(self, path: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPT), path],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_allows_home_user_project(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="orcan-validate-", dir="/tmp"
        ) as tmp:
            proc = self._run(tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_rejects_system_tree_paths(self) -> None:
        for path in ("/etc", "/usr"):
            if not Path(path).is_dir():
                continue
            with self.subTest(path=path):
                proc = self._run(path)
                self.assertNotEqual(proc.returncode, 0, proc.stderr)
                self.assertIn("sensitive path", proc.stderr)


if __name__ == "__main__":
    unittest.main()
