#!/usr/bin/env python3
"""Unit tests for compact foreground-agent labels in cockpit chrome."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "cockpit" / "src" / "orcan_cockpit" / "tmux_chrome.py"
_spec = importlib.util.spec_from_file_location("cockpit_tmux_chrome", MODULE_PATH)
tmux_chrome = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tmux_chrome)


class AgentLabelTests(unittest.TestCase):
    def test_known_binary_gets_a_friendly_label(self) -> None:
        self.assertEqual(tmux_chrome.agent_label("codex"), "Codex")
        self.assertEqual(tmux_chrome.agent_label("gemini"), "Gemini")
        self.assertEqual(tmux_chrome.agent_label("copilot"), "Copilot")

    def test_node_backed_agent_is_detected_from_commandline(self) -> None:
        self.assertEqual(
            tmux_chrome.agent_label("node", "/usr/bin/node /opt/claude-code/cli.js"),
            "Claude",
        )

    def test_shell_and_launcher_are_not_presented_as_agents(self) -> None:
        self.assertEqual(tmux_chrome.agent_label("zsh"), "")
        self.assertEqual(tmux_chrome.agent_label("agent-launcher"), "")

    def test_session_label_uses_the_active_pane_command(self) -> None:
        with patch.object(tmux_chrome, "_tmux", return_value="codex\t-"):
            self.assertEqual(tmux_chrome.session_agent_label("demo"), "Codex")

    def test_open_project_pane_uses_tmux_start_directory(self) -> None:
        result = type("Result", (), {"returncode": 0})()
        with patch.object(tmux_chrome.subprocess, "run", return_value=result) as run:
            self.assertTrue(tmux_chrome.open_project_pane("demo", "/work/project"))
        self.assertEqual(
            run.call_args.args[0],
            ["tmux", "split-window", "-v", "-t", "=demo:", "-c", "/work/project"],
        )


if __name__ == "__main__":
    unittest.main()
