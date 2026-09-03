#!/usr/bin/env python3
"""Tests for workspace-audit.py."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _scripts_loader import load_script

workspace_audit = load_script("workspace-audit.py")


class WorkspaceAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.meta = self.home / "workspaces" / "demo"
        self.meta.mkdir(parents=True)

    def _write_runtime(self) -> None:
        runtime = {
            "workspaces": [
                {
                    "name": "demo",
                    "meta_path": str(self.meta),
                    "enabled": True,
                    "projects": [{"name": "app", "path": str(self.repo.resolve())}],
                }
            ]
        }
        mounts = self.home / "mounts"
        mounts.mkdir(parents=True)
        (mounts / "runtime-config.json").write_text(
            json.dumps(runtime, indent=2) + "\n", encoding="utf-8"
        )

    def test_ok_when_symlink_matches(self) -> None:
        (self.meta / "app").symlink_to(self.repo, target_is_directory=True)
        self._write_runtime()
        findings = workspace_audit.audit(
            home=self.home,
            managed_root=None,
            compose_file=self.home / "mounts" / "compose-projects.generated.yml",
        )
        levels = {f.label: f.level for f in findings if f.label == "demo/app"}
        self.assertEqual(levels.get("demo/app"), "ok")

    def test_fail_when_real_directory_blocks(self) -> None:
        (self.meta / "app").mkdir()
        self._write_runtime()
        findings = workspace_audit.audit(
            home=self.home,
            managed_root=None,
            compose_file=self.home / "mounts" / "compose-projects.generated.yml",
        )
        blocked = [f for f in findings if f.label == "demo/app" and f.level == "fail"]
        self.assertTrue(blocked)
        self.assertIn("real directory", blocked[0].detail)

    def test_warn_when_compose_bind_missing(self) -> None:
        (self.meta / "app").symlink_to(self.repo, target_is_directory=True)
        self._write_runtime()
        compose = self.home / "mounts" / "compose-projects.generated.yml"
        compose.write_text(
            "services:\n  orcan:\n    volumes:\n      - /other:/other\n",
            encoding="utf-8",
        )
        findings = workspace_audit.audit(
            home=self.home,
            managed_root=self.tmp / "managed",
            compose_file=compose,
        )
        warns = [f for f in findings if f.label == "demo/app" and f.level == "warn"]
        self.assertTrue(warns)


if __name__ == "__main__":
    unittest.main()
