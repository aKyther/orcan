#!/usr/bin/env python3
"""Sanity checks for product version (cockpit/pyproject.toml) / release helpers."""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "cockpit" / "pyproject.toml"
VERSION_FILE = ROOT / "VERSION"
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
PYPROJECT_VERSION = re.compile(r'^version = "([0-9]+\.[0-9]+\.[0-9]+)"\s*$', re.M)


def read_pyproject_version() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    match = PYPROJECT_VERSION.search(text)
    if not match:
        raise AssertionError("cockpit/pyproject.toml missing version = \"X.Y.Z\"")
    return match.group(1)


class VersionTests(unittest.TestCase):
    def test_pyproject_version_semver(self) -> None:
        ver = read_pyproject_version()
        self.assertRegex(ver, SEMVER)

    def test_version_mirror_matches_pyproject(self) -> None:
        ver = read_pyproject_version()
        mirror = VERSION_FILE.read_text(encoding="utf-8").strip()
        self.assertEqual(mirror, ver)

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
        ver = read_pyproject_version()
        mkdocs = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
        self.assertIn(f'orcan_version: "{ver}"', mkdocs)

    def test_readme_and_home_version_match(self) -> None:
        ver = read_pyproject_version()
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        en_home = (ROOT / "docs" / "en" / "index.md").read_text(encoding="utf-8")
        pl_home = (ROOT / "docs" / "pl" / "index.md").read_text(encoding="utf-8")
        self.assertIn(f"Version **{ver}**", readme)
        self.assertIn(f"Version **{ver}**", en_home)
        self.assertIn(f"Wersja **{ver}**", pl_home)

    def test_uv_lock_package_version_matches(self) -> None:
        ver = read_pyproject_version()
        lock = (ROOT / "cockpit" / "uv.lock").read_text(encoding="utf-8")
        self.assertRegex(
            lock,
            rf'name = "orcan-cockpit"\nversion = "{re.escape(ver)}"',
        )


if __name__ == "__main__":
    unittest.main()
