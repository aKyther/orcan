#!/usr/bin/env python3
"""Public CLI contract for safe uninstall flags."""

from __future__ import annotations

import pytest

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


class UninstallCliTests(unittest.TestCase):
    def test_help_documents_purge_flags_and_project_safety(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ)
            env.update(
                {
                    "HOME": tmp,
                    "ORCAN_HOME": str(Path(tmp) / "config"),
                    "ORCAN_DATA": str(Path(tmp) / "data"),
                    "ORCAN_NO_COLOR": "1",
                }
            )
            result = subprocess.run(
                ["bash", str(ROOT / "bin" / "orcan"), "uninstall", "--help"],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--cli-only", result.stdout)
        self.assertIn("keeps all containers", result.stdout)
        self.assertIn("--purge-data", result.stdout)
        self.assertIn("--purge-images", result.stdout)
        self.assertIn("always preserves ORCAN_PROJECTS_ROOT", result.stdout)

    def test_cli_only_does_not_touch_docker_and_preserves_nested_projects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            install = home / ".local/share/orcan"
            project = install / "projects/api"
            project.mkdir(parents=True)
            (project / "app.py").write_text("project data")
            (install / "cli-files").write_text("CLI")
            config = home / "config/orcan.config.json"
            config.parent.mkdir()
            config.write_text(
                '{"workspaces":[{"projects":[{"path":"' + str(project) + '"}]}]}'
            )
            launcher = home / ".local/bin/orcan"
            launcher.parent.mkdir(parents=True)
            launcher.write_text("launcher")
            script = r"""
source "$TEST_UNINSTALL"
orcan_load_env() { :; }
orcan_warn() { :; }
orcan_info() { :; }
orcan_ok() { :; }
orcan_have() { echo 'Docker must not be queried' >&2; exit 90; }
orcan_compose_ttyd_down_all_variants() { exit 91; }
orcan_require_python() { :; }
orcan_host_python() { python3 "$@"; }
orcan_die() { echo "$*" >&2; exit 1; }
orcan_cmd_uninstall --cli-only
"""
            env = dict(
                os.environ,
                HOME=tmp,
                XDG_DATA_HOME=str(home / ".local/share"),
                ORCAN_ROOT=str(install),
                ORCAN_HOME=str(config.parent),
                ORCAN_DATA=str(home / "data"),
                ORCAN_PROJECTS_ROOT=str(home / "data/sandbox"),
                ORCAN_CONFIG_FILE=str(config),
                ORCAN_SCRIPTS=str(ROOT / "scripts/repository"),
                TEST_UNINSTALL=str(ROOT / "cli/commands/uninstall.sh"),
            )
            result = subprocess.run(
                ["bash", "-c", script],
                input="yes\n",
                text=True,
                capture_output=True,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(launcher.exists())
            self.assertFalse((install / "cli-files").exists())
            self.assertEqual((project / "app.py").read_text(), "project data")
            self.assertTrue(config.exists())

    def test_cli_only_cannot_be_combined_with_data_or_image_purge(self) -> None:
        for flag in ("--purge-data", "--purge-images"):
            result = subprocess.run(
                ["bash", str(ROOT / "bin/orcan"), "uninstall", "--cli-only", flag],
                input="yes\n",
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("cannot be combined", result.stderr)


if __name__ == "__main__":
    unittest.main()
