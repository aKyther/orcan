"""Contract tests for explicit image-agent selection and registry safety."""

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


class BuildAgentSelectionTests(unittest.TestCase):
    def test_build_requires_an_explicit_agent(self) -> None:
        result = subprocess.run(
            ["./bin/orcan", "build"], cwd=ROOT, text=True, capture_output=True, check=False
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("choose at least one agent", result.stderr)

    def test_build_deduplicates_agents_and_forwards_selection(self) -> None:
        result = run_shell(
            """
            set -Eeuo pipefail
            export ORCAN_ROOT="$PWD"
            source cli/lib/common.sh
            source cli/commands/build.sh
            orcan_require_docker() { :; }
            orcan_require_env_for_build() { :; }
            orcan_load_env() { :; }
            orcan_runtime_warn_if_config_stale() { :; }
            orcan_image_build_local() { printf '%s|%s\\n' "$1" "$2"; }
            orcan_cmd_build --agent codex --agent gemini --agent codex --no-cache
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "codex+gemini|1")

    def test_all_agents_is_the_complete_manifest_selection(self) -> None:
        result = run_shell(
            """
            set -Eeuo pipefail
            export ORCAN_ROOT="$PWD"
            source cli/lib/common.sh
            source cli/commands/build.sh
            orcan_require_docker() { :; }
            orcan_require_env_for_build() { :; }
            orcan_load_env() { :; }
            orcan_runtime_warn_if_config_stale() { :; }
            orcan_image_build_local() { printf '%s\\n' "$1"; }
            orcan_cmd_build --all-agents
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "cursor+claude+codex+gemini+copilot")


class ImageManifestTests(unittest.TestCase):
    def test_complete_manifest_is_publishable(self) -> None:
        result = run_shell(
            """
            set -Eeuo pipefail
            export ORCAN_ROOT="$PWD"
            source cli/lib/common.sh
            docker() { printf '%s\\n' '{"agents":{"cursor":true,"claude":true,"codex":true,"gemini":true,"copilot":true}}'; }
            orcan_image_has_all_agents orcan:test
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_partial_manifest_is_not_publishable(self) -> None:
        result = run_shell(
            """
            set -Eeuo pipefail
            export ORCAN_ROOT="$PWD"
            source cli/lib/common.sh
            docker() { printf '%s\\n' '{"agents":{"cursor":false,"claude":false,"codex":true,"gemini":false,"copilot":false}}'; }
            ! orcan_image_has_all_agents orcan:test
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
