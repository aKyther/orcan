#!/usr/bin/env python3
"""Tests for core settings and transactional saves that preserve workspaces."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ._scripts_loader import load_script

sw = load_script("settings-wizard.py")


class EditTmuxTests(unittest.TestCase):
    def test_updates_windows_and_prefix(self) -> None:
        cfg: dict = {
            "workspaces": [],
            "tmux": {"initial_windows": 3, "window_prefix": "tab"},
        }
        with patch("builtins.input", side_effect=["5", "win"]):
            sw.edit_tmux(cfg)
        self.assertEqual(cfg["tmux"], {"initial_windows": 5, "window_prefix": "win"})
        # workspaces untouched
        self.assertEqual(cfg["workspaces"], [])

    def test_clamps_out_of_range_windows(self) -> None:
        cfg: dict = {"workspaces": []}
        with patch("builtins.input", side_effect=["99", "tab"]):
            sw.edit_tmux(cfg)
        self.assertEqual(cfg["tmux"]["initial_windows"], 9)

    def test_invalid_number_falls_back_to_three(self) -> None:
        cfg: dict = {"workspaces": []}
        with patch("builtins.input", side_effect=["not-a-number", "tab"]):
            sw.edit_tmux(cfg)
        self.assertEqual(cfg["tmux"]["initial_windows"], 3)


class MainWorkspacesUntouchedTests(unittest.TestCase):
    def test_saving_defaults_only_leaves_workspaces_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "orcan.config.json"
            cfg_path.write_text(
                json.dumps({"workspaces": [{"name": "acme", "projects": []}]}),
                encoding="utf-8",
            )
            with (
                patch("sys.argv", ["settings-wizard.py", "--config", str(cfg_path)]),
                patch("sys.stdin.isatty", return_value=True),
                patch("builtins.input", side_effect=["n", "n", "n", "y"]),
            ):
                sw.main()
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            self.assertEqual(data["workspaces"], [{"name": "acme", "projects": []}])
            self.assertIn("tmux", data)
            self.assertNotIn("ttyd", data)
            self.assertNotIn("plugins", data)  # The user declined plugin editing.
            self.assertNotIn("storage", data)  # The user also declined storage editing.


class MainStorageSaveTests(unittest.TestCase):
    def test_storage_requires_final_save_and_preserves_workspaces(self) -> None:
        for save in (False, True):
            with self.subTest(save=save), tempfile.TemporaryDirectory() as tmp:
                cfg_path = Path(tmp) / "orcan.config.json"
                original = {"workspaces": [{"name": "acme", "projects": []}]}
                cfg_path.write_text(json.dumps(original), encoding="utf-8")
                before = cfg_path.read_bytes()
                # Skip tmux, configure storage, require its mount, skip plugins, save/discard.
                answers = [
                    "n",
                    "y",
                    "/mnt/archive/orcan-data",
                    "/mnt/archive",
                    "y",
                    "n",
                    "y" if save else "n",
                ]
                with (
                    patch(
                        "sys.argv", ["settings-wizard.py", "--config", str(cfg_path)]
                    ),
                    patch("sys.stdin.isatty", return_value=True),
                    patch("builtins.input", side_effect=answers),
                ):
                    sw.main()
                self.assertFalse((Path(tmp) / "mounts").exists())
                if not save:
                    self.assertEqual(cfg_path.read_bytes(), before)
                    continue
                data = json.loads(cfg_path.read_text())
                self.assertEqual(data["workspaces"], original["workspaces"])
                self.assertEqual(
                    data["storage"],
                    {
                        "path": "/mnt/archive/orcan-data",
                        "mount_path": "/mnt/archive",
                        "require_mount": True,
                    },
                )
                self.assertNotIn("plugins", data)

    def test_explicit_dash_disables_existing_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "orcan.config.json"
            original = {
                "workspaces": [{"name": "acme", "projects": []}],
                "storage": {
                    "path": "/mnt/archive/data",
                    "mount_path": "/mnt/archive",
                    "require_mount": True,
                },
            }
            path.write_text(json.dumps(original))
            with (
                patch("sys.argv", ["settings-wizard.py", "--config", str(path)]),
                patch("sys.stdin.isatty", return_value=True),
                patch(
                    "builtins.input", side_effect=["n", "y", "-", "-", "y", "n", "y"]
                ),
            ):
                sw.main()
            data = json.loads(path.read_text())
            self.assertEqual(
                data["storage"], {"path": "", "mount_path": "", "require_mount": True}
            )
            self.assertEqual(data["workspaces"], original["workspaces"])


class MainPluginSaveTests(unittest.TestCase):
    def test_plugin_migration_requires_final_save_and_preserves_workspaces(
        self,
    ) -> None:
        for save in (False, True):
            with self.subTest(save=save), tempfile.TemporaryDirectory() as tmp:
                cfg_path = Path(tmp) / "orcan.config.json"
                original = {
                    "workspaces": [{"name": "acme", "projects": []}],
                    "executor": {"workers": 3},
                    "ttyd": {"host_port": 17682},
                }
                cfg_path.write_text(json.dumps(original), encoding="utf-8")
                before = cfg_path.read_bytes()

                def answer(label, default=False, save=save):
                    if label == "Choose startup plugins and their settings?":
                        return True
                    if label == "Save these settings?":
                        return save
                    if label.startswith("Enable "):
                        return default
                    return False

                with (
                    patch(
                        "sys.argv", ["settings-wizard.py", "--config", str(cfg_path)]
                    ),
                    patch("sys.stdin.isatty", return_value=True),
                    patch.object(sw, "ask_yes_no", side_effect=answer),
                ):
                    sw.main()
                if not save:
                    self.assertEqual(cfg_path.read_bytes(), before)
                    continue
                data = json.loads(cfg_path.read_text())
                self.assertEqual(data["workspaces"], original["workspaces"])
                self.assertEqual(data["plugins"]["redis"]["workers"], 3)
                self.assertEqual(data["plugins"]["ttyd"]["host_port"], 17682)
                self.assertFalse(data["plugins"]["redis"]["enabled"])
                self.assertNotIn("executor", data)
                self.assertNotIn("ttyd", data)


if __name__ == "__main__":
    unittest.main()
