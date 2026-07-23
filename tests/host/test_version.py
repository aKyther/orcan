#!/usr/bin/env python3
"""Sanity checks for VERSION / release helpers."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class VersionTests(unittest.TestCase):
    def test_version_file_semver(self) -> None:
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertRegex(ver, r"^[0-9]+\.[0-9]+\.[0-9]+$")

    def test_release_check_ok(self) -> None:
        proc = subprocess.run(
            [str(ROOT / "scripts" / "repository" / "release.sh"), "check"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("VERSION OK", proc.stdout)

    def test_mkdocs_extra_version_matches(self) -> None:
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        mkdocs = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
        self.assertIn(f'orcan_version: "{ver}"', mkdocs)

    def test_readme_and_home_version_match(self) -> None:
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        en_home = (ROOT / "docs" / "en" / "index.md").read_text(encoding="utf-8")
        pl_home = (ROOT / "docs" / "pl" / "index.md").read_text(encoding="utf-8")
        self.assertIn(f"Version **{ver}**", readme)
        self.assertIn(f"Version **{ver}**", en_home)
        self.assertIn(f"Wersja **{ver}**", pl_home)


if __name__ == "__main__":
    unittest.main()
