#!/usr/bin/env python3
"""Public CLI contract for safe uninstall flags."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class UninstallCliTests(unittest.TestCase):
    def test_help_documents_purge_flags_and_project_safety(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ)
            env.update(
                {
                    "HOME": tmp,
                    "ORCAN_HOME": str(Path(tmp) / "config"),
                    "ORCAN_DATA": str(Path(tmp) / "data"),
                    "ORCAN_NO_COLOR": "1",
                }
            )
            result = subprocess.run(
                ["bash", str(ROOT / "bin" / "orcan"), "uninstall", "--help"],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--purge-data", result.stdout)
        self.assertIn("--purge-images", result.stdout)
        self.assertIn("always preserves ORCAN_PROJECTS_ROOT", result.stdout)


if __name__ == "__main__":
    unittest.main()
