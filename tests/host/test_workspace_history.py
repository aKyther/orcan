#!/usr/bin/env python3
"""Tests for per-workspace shell history path helpers."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docker" / "rootfs" / "etc" / "orcan" / "shell" / "workspace-history.sh"


def _run(*args: str, env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(
        ["bash", "-c", f'source "{SCRIPT}"; ' + " ".join(args)],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return proc.stdout.strip()


class WorkspaceHistoryTests(unittest.TestCase):
    def test_sanitize_workspace_name(self) -> None:
        self.assertEqual(_run('orcan_sanitize_workspace_name "orcan-dev"'), "orcan-dev")
        self.assertEqual(_run('orcan_sanitize_workspace_name "feat/foo"'), "feat_foo")

    def test_histfile_path_per_workspace(self) -> None:
        path = _run(
            'orcan_workspace_histfile_path "demo" zsh',
            env={"HOME": "/home/developer"},
        )
        self.assertEqual(
            path,
            "/home/developer/.local/share/orcan/history/workspaces/demo/.zsh_history",
        )

    def test_apply_uses_orcan_workspace_name(self) -> None:
        out = subprocess.run(
            [
                "bash",
                "-c",
                f'source "{SCRIPT}"; '
                "export ORCAN_WORKSPACE_NAME='my-ws'; "
                "orcan_apply_workspace_histfile; "
                'printf "%s" "$HISTFILE"',
            ],
            capture_output=True,
            text=True,
            check=True,
            env={"HOME": "/home/developer"},
        )
        self.assertIn("/history/workspaces/my-ws/", out.stdout)
        self.assertTrue(
            out.stdout.endswith(".bash_history") or out.stdout.endswith(".zsh_history")
        )


if __name__ == "__main__":
    unittest.main()
