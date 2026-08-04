#!/usr/bin/env python3
"""Unit tests for claude_hook: enable/disable/status merge into .claude/settings.json."""

from __future__ import annotations

import json
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

    def test_project_paths_from_config_flattens_workspaces(self) -> None:
        config_path = Path(self._tmp.name) / "orcan.config.json"
        config_path.write_text(
            json.dumps(
                {
                    "workspaces": [
                        {
                            "name": "ws",
                            "projects": [
                                {"name": "a", "path": "/tmp/a"},
                                {"name": "b", "path": "/tmp/b"},
                            ],
                        }
                    ]
                }
            )
        )
        paths = ch.project_paths_from_config(config_path)
        self.assertEqual(paths, [Path("/tmp/a"), Path("/tmp/b")])


if __name__ == "__main__":
    unittest.main()
