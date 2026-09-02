#!/usr/bin/env python3
"""Tests for ephemeral cockpit reconnect state."""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "cockpit_state", ROOT / "cockpit" / "src" / "orcan_cockpit" / "state.py"
)
assert SPEC is not None and SPEC.loader is not None
state = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(state)


class CockpitStateTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "last-session"
            with mock.patch.dict(os.environ, {"ORCAN_COCKPIT_STATE_PATH": str(path)}):
                self.assertIsNone(state.read_last_session())
                state.remember_session("workspace-one")
                self.assertEqual(state.read_last_session(), "workspace-one")

    def test_invalid_state_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "last-session"
            path.write_text("one\ntwo\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"ORCAN_COCKPIT_STATE_PATH": str(path)}):
                self.assertIsNone(state.read_last_session())

    def test_write_failure_does_not_break_attach(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "directory"
            directory.mkdir()
            with mock.patch.dict(
                os.environ, {"ORCAN_COCKPIT_STATE_PATH": str(directory)}
            ):
                state.remember_session("workspace-one")


if __name__ == "__main__":
    unittest.main()
