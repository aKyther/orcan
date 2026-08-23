#!/usr/bin/env python3
"""Tests for scripts/repository/path_guards.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "repository"))

from path_guards import is_sensitive_path  # noqa: E402


class SensitivePathTests(unittest.TestCase):
    def test_exact_roots(self) -> None:
        for p in ("/", "/home", "/root", "/etc", "/usr", "/var", "/opt"):
            with self.subTest(p=p):
                self.assertTrue(is_sensitive_path(p), p)

    def test_tree_under_system_roots(self) -> None:
        for p in (
            "/var/lib/docker",
            "/etc/passwd",
            "/usr/local",
            "/opt/homebrew",
            "/root/.ssh",
        ):
            with self.subTest(p=p):
                self.assertTrue(is_sensitive_path(p), p)

    def test_home_user_projects_allowed(self) -> None:
        # Resolve may differ on missing paths — still must not treat as /home.
        self.assertFalse(is_sensitive_path("/home/developer/code/app"))
        self.assertFalse(is_sensitive_path("/home/ubuntu/workspace/orcan"))

    def test_developer_workspaces_allowed(self) -> None:
        self.assertFalse(
            is_sensitive_path("/home/developer/workspaces/my-ws")
        )


if __name__ == "__main__":
    unittest.main()
