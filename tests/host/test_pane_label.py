#!/usr/bin/env python3
"""Host tests for tmux pane-label.sh (friendly live pane titles)."""

from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docker" / "rootfs" / "etc" / "tmux" / "scripts" / "pane-label.sh"
BASH = shutil.which("bash") or "/bin/bash"


class PaneLabelScriptTests(unittest.TestCase):
    def _label(self, cmd: str, cmdline: str = "") -> str:
        env = os.environ.copy()
        env["PANE_LABEL_CMD"] = cmd
        env["PANE_LABEL_CMDLINE"] = cmdline
        out = subprocess.check_output(["bash", str(SCRIPT)], env=env, text=True)
        return out.strip()

    def _label_argv(self, *args: str, env: dict[str, str] | None = None) -> str:
        run_env = {k: v for k, v in os.environ.items() if not k.startswith("PANE_LABEL_")}
        if env is not None:
            run_env = env
        out = subprocess.check_output([BASH, str(SCRIPT), *args], env=run_env, text=True)
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

    # --- argv path (native tmux format vars: pane_current_command, pane_pid) ---

    def test_argv_command_is_matched(self) -> None:
        self.assertEqual(self._label_argv("codex"), "codex")
        self.assertEqual(self._label_argv("node"), "node")
        self.assertEqual(self._label_argv("/usr/local/bin/agent"), "agent")
        self.assertEqual(self._label_argv(), "zsh")

    def test_argv_pid_resolves_agent_from_proc_cmdline(self) -> None:
        proc = subprocess.Popen(["bash", "-c", "exec -a 'node /opt/claude/cli.js' sleep 30"])
        try:
            self.assertEqual(self._label_argv("node", str(proc.pid)), "claude")
        finally:
            proc.kill()
            proc.wait()

    def test_hot_path_spawns_no_external_process(self) -> None:
        # A border redraw for an agent pane must not fork tmux/coreutils:
        # runs with an empty PATH and still labels correctly.
        self.assertEqual(self._label_argv("codex", "", env={"PATH": "/nonexistent"}), "codex")


if __name__ == "__main__":
    unittest.main()
