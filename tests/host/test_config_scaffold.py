"""Regression tests for idempotent ``orcan init PATH`` scaffolding."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCAFFOLD = ROOT / "scripts" / "repository" / "config-scaffold.py"


class ConfigScaffoldTests(unittest.TestCase):
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
