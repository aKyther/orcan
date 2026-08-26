#!/usr/bin/env python3
"""Unit tests for orcan.context_model_check."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "docker" / "rootfs" / "usr" / "local" / "lib"))

from orcan import context_model_check as mc  # noqa: E402


class ModelCheckTests(unittest.TestCase):
    def test_quick_mode_skips_probe(self) -> None:
        with mock.patch.object(mc.shutil, "which", return_value="/usr/bin/claude"):
            with mock.patch.object(mc.subprocess, "run") as run:
                run.return_value = mock.Mock(returncode=0, stdout="1.0.0\n", stderr="")
                result = mc.check_recap_model(probe=False)
        self.assertTrue(result["ok"])
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["/usr/bin/claude", "--version"])

    def test_probe_success_runs_exact_prompt(self) -> None:
        with mock.patch.object(mc.shutil, "which", return_value="/usr/bin/claude"):
            with mock.patch.object(mc.subprocess, "run") as run:
                run.side_effect = [
                    mock.Mock(returncode=0, stdout="1.0.0\n", stderr=""),
                    mock.Mock(returncode=0, stdout="OK\n", stderr=""),
                ]
                result = mc.check_recap_model()
        self.assertTrue(result["ok"])
        self.assertEqual(result["detail"], "probe ok (haiku)")
        self.assertEqual(run.call_args_list[1].args[0], ["/usr/bin/claude", "-p", "--model", "haiku", "Reply with exactly: OK"])

    def test_probe_failure_is_reported_without_raising(self) -> None:
        with mock.patch.object(mc.shutil, "which", return_value="/usr/bin/claude"):
            with mock.patch.object(mc.subprocess, "run") as run:
                run.side_effect = [
                    mock.Mock(returncode=0, stdout="1.0.0\n", stderr=""),
                    mock.Mock(returncode=2, stdout="", stderr="quota exceeded\n"),
                ]
                result = mc.check_recap_model()
        self.assertFalse(result["ok"])
        self.assertIn("exited 2", result["detail"])
        self.assertIn("quota exceeded", result["detail"])

    def test_environment_can_disable_probe(self) -> None:
        with mock.patch.dict("os.environ", {"ORCAN_CONTEXT_MODEL_PROBE": "0"}):
            with mock.patch.object(mc.shutil, "which", return_value="/usr/bin/claude"):
                with mock.patch.object(mc.subprocess, "run") as run:
                    run.return_value = mock.Mock(returncode=0, stdout="1.0.0\n", stderr="")
                    result = mc.check_recap_model(probe=None)
        self.assertTrue(result["ok"])
        run.assert_called_once()

    def test_probe_timeout_is_reported_without_raising(self) -> None:
        with mock.patch.object(mc.shutil, "which", return_value="/usr/bin/claude"):
            with mock.patch.object(mc.subprocess, "run") as run:
                run.side_effect = [
                    mock.Mock(returncode=0, stdout="1.0.0\n", stderr=""),
                    mc.subprocess.TimeoutExpired(cmd="claude", timeout=mc.PROBE_TIMEOUT),
                ]
                result = mc.check_recap_model()
        self.assertFalse(result["ok"])
        self.assertIn("probe failed", result["detail"])


if __name__ == "__main__":
    unittest.main()
