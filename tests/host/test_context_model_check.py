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


if __name__ == "__main__":
    unittest.main()
