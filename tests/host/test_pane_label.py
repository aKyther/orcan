#!/usr/bin/env python3
"""Host tests for tmux pane-label.sh (friendly live pane titles)."""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docker" / "rootfs" / "etc" / "tmux" / "scripts" / "pane-label.sh"


class PaneLabelScriptTests(unittest.TestCase):
    def _label(self, cmd: str, cmdline: str = "") -> str:
        env = os.environ.copy()
        env["PANE_LABEL_CMD"] = cmd
        env["PANE_LABEL_CMDLINE"] = cmdline
        out = subprocess.check_output(["bash", str(SCRIPT)], env=env, text=True)
        return out.strip()

    def test_script_is_present(self) -> None:
        self.assertTrue(SCRIPT.is_file())


    def test_claude_from_command(self) -> None:
        self.assertEqual(self._label("claude"), "claude")

    def test_claude_under_node_cmdline(self) -> None:
        self.assertEqual(
            self._label("node", "/usr/bin/node /opt/claude/cli.js --resume"),
            "claude",
        )

    def test_codex_and_aider(self) -> None:
        self.assertEqual(self._label("codex"), "codex")
        self.assertEqual(self._label("python", "python -m aider"), "aider")

    def test_bare_agent_command(self) -> None:
        self.assertEqual(self._label("agent"), "agent")

    def test_agent_path_uses_basename(self) -> None:
        self.assertEqual(self._label("/usr/local/bin/agent"), "agent")

    def test_fallback_basename(self) -> None:
        self.assertEqual(self._label("/usr/bin/zsh"), "zsh")

    def test_empty_falls_back_to_zsh(self) -> None:
        self.assertEqual(self._label(""), "zsh")


if __name__ == "__main__":
    unittest.main()
