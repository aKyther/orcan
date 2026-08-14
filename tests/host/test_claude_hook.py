#!/usr/bin/env python3
"""Unit tests for claude_hook: enable/disable/status merge into .claude/settings.json."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "repository"))

import claude_hook as ch  # noqa: E402


class ClaudeHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name) / "proj"
        self.project.mkdir()
        self.settings = ch.settings_path(self.project)

    def test_status_disabled_when_no_settings_file(self) -> None:
        self.assertEqual(ch.status(self.project), "disabled")

    def test_enable_creates_settings_with_hook(self) -> None:
        result = ch.enable(self.project, dry_run=False)
        self.assertEqual(result, "enabled")
        data = json.loads(self.settings.read_text())
        self.assertTrue(ch.has_hook(data))
        self.assertEqual(ch.status(self.project), "enabled")

    def test_enable_is_idempotent(self) -> None:
        ch.enable(self.project, dry_run=False)
        result = ch.enable(self.project, dry_run=False)
        self.assertEqual(result, "already enabled")
        data = json.loads(self.settings.read_text())
        self.assertEqual(len(data["hooks"]["Stop"]), 1)

    def test_enable_preserves_existing_keys(self) -> None:
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(
            json.dumps({"permissions": {"deny": ["Read(**/.env)"]}})
        )
        ch.enable(self.project, dry_run=False)
        data = json.loads(self.settings.read_text())
        self.assertEqual(data["permissions"]["deny"], ["Read(**/.env)"])
        self.assertTrue(ch.has_hook(data))

    def test_enable_backs_up_existing_file(self) -> None:
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text("{}")
        ch.enable(self.project, dry_run=False)
        backups = list(self.settings.parent.glob("settings.json.bak.*"))
        self.assertEqual(len(backups), 1)

    def test_dry_run_enable_writes_nothing(self) -> None:
        result = ch.enable(self.project, dry_run=True)
        self.assertEqual(result, "would enable")
        self.assertFalse(self.settings.exists())

    @unittest.skipIf(os.geteuid() == 0, "root bypasses file permission checks")
    def test_enable_gives_clear_error_on_permission_denied(self) -> None:
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text("{}")
        self.settings.chmod(0o444)
        self.addCleanup(self.settings.chmod, 0o644)
        with self.assertRaises(SystemExit):
            ch.enable(self.project, dry_run=False)

    def test_disable_removes_hook_and_empty_containers(self) -> None:
        ch.enable(self.project, dry_run=False)
        result = ch.disable(self.project, dry_run=False)
        self.assertEqual(result, "disabled")
        data = json.loads(self.settings.read_text())
        self.assertNotIn("hooks", data)

    def test_disable_keeps_other_hooks(self) -> None:
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(
            json.dumps(
                {
                    "hooks": {
                        "Stop": [
                            {"hooks": [{"type": "command", "command": "other-tool"}]}
                        ]
                    }
                }
            )
        )
        ch.enable(self.project, dry_run=False)
        ch.disable(self.project, dry_run=False)
        data = json.loads(self.settings.read_text())
        commands = [h["command"] for e in data["hooks"]["Stop"] for h in e["hooks"]]
        self.assertEqual(commands, ["other-tool"])

    def test_disable_without_settings_file_is_noop(self) -> None:
        self.assertEqual(ch.disable(self.project, dry_run=False), "already disabled")

    def test_disable_is_idempotent(self) -> None:
        ch.enable(self.project, dry_run=False)
        ch.disable(self.project, dry_run=False)
        self.assertEqual(ch.disable(self.project, dry_run=False), "already disabled")

    def write_manifest(self, home: Path, workspaces: list[dict]) -> None:
        (home / "workspaces").mkdir(parents=True, exist_ok=True)
        (home / "workspaces" / "index.json").write_text(
            json.dumps({"workspaces": workspaces})
        )

    def test_workspace_meta_paths_returns_all_by_default(self) -> None:
        home = Path(self._tmp.name) / "home"
        self.write_manifest(
            home,
            [
                {"name": "ws1", "meta_path": "/tmp/ws1"},
                {"name": "ws2", "meta_path": "/tmp/ws2"},
            ],
        )
        self.assertEqual(
            ch.workspace_meta_paths(home),
            [("ws1", Path("/tmp/ws1")), ("ws2", Path("/tmp/ws2"))],
        )

    def test_workspace_meta_paths_filters_by_name(self) -> None:
        home = Path(self._tmp.name) / "home"
        self.write_manifest(
            home,
            [
                {"name": "ws1", "meta_path": "/tmp/ws1"},
                {"name": "ws2", "meta_path": "/tmp/ws2"},
            ],
        )
        self.assertEqual(
            ch.workspace_meta_paths(home, ["ws2"]),
            [("ws2", Path("/tmp/ws2"))],
        )

    def test_workspace_meta_paths_unknown_name_dies(self) -> None:
        home = Path(self._tmp.name) / "home"
        self.write_manifest(home, [{"name": "ws1", "meta_path": "/tmp/ws1"}])
        with self.assertRaises(SystemExit):
            ch.workspace_meta_paths(home, ["nope"])

    def test_workspace_meta_paths_missing_manifest_dies(self) -> None:
        home = Path(self._tmp.name) / "home-unsynced"
        with self.assertRaises(SystemExit):
            ch.workspace_meta_paths(home)

    def write_manifest_with_projects(
        self, home: Path, ws_name: str, meta_path: Path, project_path: Path
    ) -> None:
        self.write_manifest(
            home,
            [
                {
                    "name": ws_name,
                    "meta_path": str(meta_path),
                    "projects": [{"name": "proj", "path": str(project_path)}],
                }
            ],
        )

    def test_infer_workspace_from_cwd_matches_project_root(self) -> None:
        home = Path(self._tmp.name) / "home"
        registered = Path(self._tmp.name) / "registered-proj"
        registered.mkdir()
        self.write_manifest_with_projects(home, "ws1", Path("/tmp/ws1"), registered)
        self.assertEqual(ch.infer_workspace_from_cwd(home, registered), "ws1")

    def test_infer_workspace_from_cwd_matches_subdirectory(self) -> None:
        home = Path(self._tmp.name) / "home"
        registered = Path(self._tmp.name) / "registered-proj"
        (registered / "sub" / "dir").mkdir(parents=True)
        self.write_manifest_with_projects(home, "ws1", Path("/tmp/ws1"), registered)
        self.assertEqual(
            ch.infer_workspace_from_cwd(home, registered / "sub" / "dir"), "ws1"
        )

    def test_infer_workspace_from_cwd_no_match_returns_none(self) -> None:
        home = Path(self._tmp.name) / "home"
        registered = Path(self._tmp.name) / "registered-proj"
        unrelated = Path(self._tmp.name) / "elsewhere"
        registered.mkdir()
        unrelated.mkdir()
        self.write_manifest_with_projects(home, "ws1", Path("/tmp/ws1"), registered)
        self.assertIsNone(ch.infer_workspace_from_cwd(home, unrelated))

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        script = ROOT / "scripts" / "repository" / "claude_hook.py"
        return subprocess.run(
            [sys.executable, str(script), *args], capture_output=True, text=True
        )

    def test_cli_status_with_no_args_shows_every_workspace(self) -> None:
        home = Path(self._tmp.name) / "home"
        ws1, ws2 = Path(self._tmp.name) / "ws1", Path(self._tmp.name) / "ws2"
        ws1.mkdir()
        ws2.mkdir()
        self.write_manifest(
            home,
            [
                {"name": "ws1", "meta_path": str(ws1)},
                {"name": "ws2", "meta_path": str(ws2)},
            ],
        )
        result = self.run_cli("status", "--home", str(home))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ws1", result.stdout)
        self.assertIn("ws2", result.stdout)
        self.assertIn(str(ws1), result.stdout)
        self.assertIn(str(ws2), result.stdout)

    def test_cli_enable_with_no_args_requires_name_or_all_when_multiple(self) -> None:
        home = Path(self._tmp.name) / "home"
        ws1, ws2 = Path(self._tmp.name) / "ws1", Path(self._tmp.name) / "ws2"
        ws1.mkdir()
        ws2.mkdir()
        self.write_manifest(
            home,
            [
                {"name": "ws1", "meta_path": str(ws1)},
                {"name": "ws2", "meta_path": str(ws2)},
            ],
        )
        result = self.run_cli("enable", "--home", str(home))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("specify name(s) or --all", result.stderr)
        self.assertFalse(ch.has_hook(ch.load_settings(ch.settings_path(ws1))))
        self.assertFalse(ch.has_hook(ch.load_settings(ch.settings_path(ws2))))

    def test_cli_status_from_inside_a_project_scopes_to_its_workspace(self) -> None:
        home = Path(self._tmp.name) / "home"
        ws1, ws2 = Path(self._tmp.name) / "ws1", Path(self._tmp.name) / "ws2"
        proj1 = Path(self._tmp.name) / "proj1"
        ws1.mkdir()
        ws2.mkdir()
        proj1.mkdir()
        self.write_manifest(
            home,
            [
                {
                    "name": "ws1",
                    "meta_path": str(ws1),
                    "projects": [{"name": "proj1", "path": str(proj1)}],
                },
                {"name": "ws2", "meta_path": str(ws2)},
            ],
        )
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "repository" / "claude_hook.py"),
             "status", "--home", str(home)],
            capture_output=True, text=True, cwd=str(proj1),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ws1", result.stdout)
        self.assertNotIn("ws2", result.stdout)
        self.assertNotIn("Note:", result.stdout)

    def test_cli_status_from_unrelated_cwd_notes_and_shows_all(self) -> None:
        home = Path(self._tmp.name) / "home"
        ws1, ws2 = Path(self._tmp.name) / "ws1", Path(self._tmp.name) / "ws2"
        unrelated = Path(self._tmp.name) / "elsewhere"
        ws1.mkdir()
        ws2.mkdir()
        unrelated.mkdir()
        self.write_manifest(
            home,
            [
                {"name": "ws1", "meta_path": str(ws1)},
                {"name": "ws2", "meta_path": str(ws2)},
            ],
        )
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "repository" / "claude_hook.py"),
             "status", "--home", str(home)],
            capture_output=True, text=True, cwd=str(unrelated),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Note:", result.stdout)
        self.assertIn("not inside any registered project", result.stdout)
        self.assertIn("ws1", result.stdout)
        self.assertIn("ws2", result.stdout)


if __name__ == "__main__":
    unittest.main()
