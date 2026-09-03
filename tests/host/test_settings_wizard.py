#!/usr/bin/env python3
"""Unit tests for settings-wizard.py: tmux/ttyd editing, split out of
config-wizard.py so it never touches "workspaces"."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from _scripts_loader import load_script

sw = load_script("settings-wizard.py")


class EditTmuxTests(unittest.TestCase):
    def test_updates_windows_and_prefix(self) -> None:
        cfg: dict = {"workspaces": [], "tmux": {"initial_windows": 3, "window_prefix": "tab"}}
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


class EditTtydTests(unittest.TestCase):
    def test_updates_port_and_font(self) -> None:
        cfg: dict = {"workspaces": []}
        with patch("builtins.input", side_effect=["8080", "8080", "127.0.0.1", "22"]):
            sw.edit_ttyd(cfg)
        self.assertEqual(cfg["ttyd"]["port"], 8080)
        self.assertEqual(cfg["ttyd"]["host_port"], 8080)
        self.assertEqual(cfg["ttyd"]["bind"], "127.0.0.1")
        self.assertEqual(cfg["ttyd"]["font_size"], 22)

    def test_invalid_numbers_leave_settings_unchanged(self) -> None:
        cfg: dict = {"workspaces": [], "ttyd": dict(sw.DEFAULT_TTYD)}
        with patch("builtins.input", side_effect=["nope", "nope", "nope", "nope"]):
            sw.edit_ttyd(cfg)
        self.assertEqual(cfg["ttyd"], sw.DEFAULT_TTYD)


class MainWorkspacesUntouchedTests(unittest.TestCase):
    def test_saving_defaults_only_leaves_workspaces_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "orcan.config.json"
            cfg_path.write_text(
                json.dumps({"workspaces": [{"name": "acme", "projects": []}]}),
                encoding="utf-8",
            )
            with patch("sys.argv", ["settings-wizard.py", "--config", str(cfg_path)]), patch(
                "sys.stdin.isatty", return_value=True
            ), patch("builtins.input", side_effect=["n", "n", "y"]):
                sw.main()
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            self.assertEqual(data["workspaces"], [{"name": "acme", "projects": []}])
            self.assertIn("tmux", data)
            self.assertIn("ttyd", data)


if __name__ == "__main__":
    unittest.main()
