#!/usr/bin/env python3
"""Tests for orcan-context-scan --all-workspaces helpers and supervisord mode render."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "docker" / "rootfs" / "usr" / "local" / "bin" / "orcan-context-scan"
SUPERVISORD_BIN = ROOT / "docker" / "rootfs" / "usr" / "local" / "bin" / "orcan-supervisord"
CONF_D = ROOT / "docker" / "rootfs" / "etc" / "orcan" / "supervisor.d"
TEMPLATE = ROOT / "docker" / "rootfs" / "etc" / "orcan" / "supervisord.conf"

sys.path.insert(0, str(ROOT / "docker" / "rootfs" / "usr" / "local" / "lib"))

_loader = importlib.machinery.SourceFileLoader("orcan_context_scan", str(SCRIPT_PATH))
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
scan = importlib.util.module_from_spec(_spec)
_loader.exec_module(scan)


class AllWorkspacesTests(unittest.TestCase):
    def test_lists_existing_enabled_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root_a = Path(tmp) / "ws-a"
            root_b = Path(tmp) / "ws-b"
            root_a.mkdir()
            root_b.mkdir()
            cfg = {
                "workspaces": [
                    {"name": "a", "root": str(root_a), "projects": []},
                    {"name": "b", "root": str(root_b), "enabled": False, "projects": []},
                    {"name": "missing", "root": str(Path(tmp) / "nope"), "projects": []},
                ]
            }
            cfg_path = Path(tmp) / "config.json"
            cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
            with mock.patch.dict(os.environ, {"ORCAN_CONFIG": str(cfg_path)}):
                roots = scan.all_workspace_roots()
            self.assertEqual(roots, [root_a.resolve()])


class SupervisordRenderTests(unittest.TestCase):
    def _render(self, mode: str, *, context_scan: str = "1") -> tuple[Path, set[str]]:
        tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        state = Path(tmp) / "state"
        env = {
            **os.environ,
            "ORCAN_SUPERVISOR_MODE": mode,
            "ORCAN_SUPERVISOR_CONF_D": str(CONF_D),
            "ORCAN_SUPERVISOR_CONF_TEMPLATE": str(TEMPLATE),
            "ORCAN_SUPERVISOR_STATE_D": str(state),
            "ORCAN_SUPERVISOR_DRY_RUN": "1",
            "ORCAN_CONTEXT_SCAN": context_scan,
        }
        proc = subprocess.run(
            ["bash", str(SUPERVISORD_BIN)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        programs = state / "programs"
        names = {p.name for p in programs.glob("*.conf")} if programs.is_dir() else set()
        return state, names

    def test_keepalive_mode_includes_keepalive_and_scan(self) -> None:
        state, names = self._render("keepalive")
        self.assertEqual(names, {"keepalive.conf", "context-scan.conf"})
        self.assertTrue((state / "supervisord.conf").is_file())
        self.assertTrue((state / "supervisord.log").is_file())
        self.assertTrue((state / "README.md").is_file())
        scan_conf = (state / "programs" / "context-scan.conf").read_text(encoding="utf-8")
        self.assertIn(str(state / "childlog"), scan_conf)

    def test_ttyd_mode_includes_ttyd_and_scan(self) -> None:
        _, names = self._render("ttyd")
        self.assertEqual(names, {"ttyd.conf", "context-scan.conf"})

    def test_context_scan_can_be_disabled(self) -> None:
        _, names = self._render("keepalive", context_scan="0")
        self.assertEqual(names, {"keepalive.conf"})


if __name__ == "__main__":
    unittest.main()
