"""Contract tests for native workspace tmux attachment."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run_shell(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


class AttachCliTests(unittest.TestCase):
    def test_attach_resolves_workspace_before_starting_tmux(self) -> None:
        result = run_shell(
            """
            set -Eeuo pipefail
            export ORCAN_ROOT="$PWD"
            export ORCAN_CLI_DIR="$PWD/cli"
            source cli/lib/common.sh
            source cli/commands/attach.sh
            orcan_require_docker() { :; }
            orcan_record_workspace_use() { :; }
            orcan_info() { :; }
            orcan_enter_exec() {
                if [[ "$1" == "orcan-workspaces" ]]; then
                    printf 'Main workspace\\t/workspace/main\\tmain-session\\trepo\\n'
                    return 0
                fi
                printf '%s|' "$@"
            }
            orcan_cmd_attach 'Main workspace'
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout,
            "cursor-tmux-workspace-attach|main-session|/workspace/main|Main workspace|",
        )

    def test_attach_help_is_available_from_the_public_cli(self) -> None:
        result = subprocess.run(
            ["./bin/orcan", "attach", "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ssh -tt my-enclave", result.stdout)

    def test_attach_rejects_an_unknown_workspace_without_starting_tmux(self) -> None:
        result = run_shell(
            """
            set -Eeuo pipefail
            export ORCAN_ROOT="$PWD"
            export ORCAN_CLI_DIR="$PWD/cli"
            source cli/lib/common.sh
            source cli/commands/attach.sh
            orcan_require_docker() { :; }
            orcan_enter_exec() {
                [[ "$1" == "orcan-workspaces" ]] && printf 'Known\\t/workspace/known\\tknown\\trepo\\n'
            }
            orcan_cmd_attach missing
            """
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("workspace not found: missing", result.stderr)


if __name__ == "__main__":
    unittest.main()
