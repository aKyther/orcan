#!/usr/bin/env python3
"""Unit tests for `orcan migrate` (scripts/repository/migrate_projects.py)."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "repository"
sys.path.insert(0, str(SCRIPTS))

_spec = importlib.util.spec_from_file_location(
    "migrate_projects", SCRIPTS / "migrate_projects.py"
)
assert _spec and _spec.loader
migrate_projects = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate_projects)


def _init_repo(path: Path) -> None:
    import subprocess

    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--quiet", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True, capture_output=True)
    (path / "f.txt").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


class PlanMovesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.managed_root = self.tmp / "managed"

    def test_project_outside_managed_root_is_planned(self) -> None:
        cfg = {
            "workspaces": [
                {
                    "name": "ws",
                    "projects": [{"name": "app", "path": str(self.tmp / "external" / "app")}],
                }
            ]
        }
        moves = migrate_projects.plan_moves(cfg, self.managed_root)
        self.assertEqual(len(moves), 1)
        _project, old_path, new_path = moves[0]
        self.assertEqual(old_path, self.tmp / "external" / "app")
        self.assertEqual(new_path, self.managed_root / "ws" / "app")

    def test_project_already_under_managed_root_is_skipped(self) -> None:
        already = self.managed_root / "ws" / "app"
        cfg = {"workspaces": [{"name": "ws", "projects": [{"name": "app", "path": str(already)}]}]}
        moves = migrate_projects.plan_moves(cfg, self.managed_root)
        self.assertEqual(moves, [])


class ApplyMovesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.managed_root = self.tmp / "managed"

    def test_moves_repo_preserving_git_history_and_leaves_symlink(self) -> None:
        old_path = self.tmp / "external" / "app"
        _init_repo(old_path)
        new_path = self.managed_root / "ws" / "app"
        project = {"name": "app", "path": str(old_path)}

        log = migrate_projects.apply_moves([(project, old_path, new_path)], leave_symlink=True)

        self.assertTrue(new_path.is_dir())
        self.assertTrue((new_path / ".git").exists())
        self.assertTrue((new_path / "f.txt").is_file())
        self.assertEqual(project["path"], str(new_path))
        self.assertTrue(old_path.is_symlink())
        self.assertEqual(old_path.resolve(), new_path.resolve())
        self.assertTrue(any("moved:" in line for line in log))

    def test_no_symlink_when_disabled(self) -> None:
        old_path = self.tmp / "external" / "app"
        _init_repo(old_path)
        new_path = self.managed_root / "ws" / "app"
        project = {"name": "app", "path": str(old_path)}

        migrate_projects.apply_moves([(project, old_path, new_path)], leave_symlink=False)

        self.assertFalse(old_path.exists())
        self.assertTrue(new_path.is_dir())

    def test_skips_when_destination_already_exists(self) -> None:
        old_path = self.tmp / "external" / "app"
        _init_repo(old_path)
        new_path = self.managed_root / "ws" / "app"
        new_path.mkdir(parents=True)
        project = {"name": "app", "path": str(old_path)}

        log = migrate_projects.apply_moves([(project, old_path, new_path)], leave_symlink=True)

        self.assertTrue(old_path.is_dir())
        self.assertTrue(any("skip" in line for line in log))
        self.assertEqual(project["path"], str(old_path))


class MainDryRunTests(unittest.TestCase):
    def test_dry_run_does_not_move_or_write_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proj = root / "app"
            _init_repo(proj)
            cfg_path = root / "orcan.config.json"
            cfg = {"workspaces": [{"name": "ws", "projects": [{"name": "app", "path": str(proj)}]}]}
            cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

            old_argv = sys.argv
            try:
                sys.argv = [
                    "migrate_projects.py",
                    "--root", str(root),
                    "--config", str(cfg_path),
                    "--managed-root", str(root / "managed"),
                ]
                rc = migrate_projects.main()
            finally:
                sys.argv = old_argv

            self.assertEqual(rc, 0)
            self.assertTrue(proj.is_dir())
            self.assertFalse((root / "managed").exists())
            self.assertEqual(
                json.loads(cfg_path.read_text(encoding="utf-8"))["workspaces"][0]["projects"][0]["path"],
                str(proj),
            )


if __name__ == "__main__":
    unittest.main()
