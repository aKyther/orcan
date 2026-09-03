#!/usr/bin/env python3
"""Tests for host-side workspace reconcile (reconcile-host.py)."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from _scripts_loader import load_script

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "docker" / "rootfs" / "usr" / "local" / "lib"

reconcile_host = load_script("reconcile-host.py")

_reconcile_spec = importlib.util.spec_from_file_location(
    "orcan_reconcile_module", LIB / "orcan" / "reconcile.py"
)
assert _reconcile_spec and _reconcile_spec.loader
_reconcile = importlib.util.module_from_spec(_reconcile_spec)
sys.modules[_reconcile_spec.name] = _reconcile
_reconcile_spec.loader.exec_module(_reconcile)


class HostCfgTests(unittest.TestCase):
    def test_maps_meta_path_and_workspace_paths(self) -> None:
        runtime = {
            "workspaces": [
                {
                    "name": "demo",
                    "root": "/home/developer/workspaces/demo",
                    "meta_path": "/meta/demo",
                    "projects": [
                        {
                            "name": "app",
                            "path": "/repos/app",
                            "workspace_path": "/home/developer/workspaces/demo/app",
                        }
                    ],
                }
            ]
        }
        cfg = reconcile_host.host_cfg_from_runtime(runtime)
        ws = cfg["workspaces"][0]
        self.assertEqual(ws["root"], "/meta/demo")
        self.assertEqual(ws["projects"][0]["workspace_path"], "/meta/demo/app")


class HostReconcileIntegrationTests(unittest.TestCase):
    def test_reconcile_on_host_meta_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo = base / "repo"
            repo.mkdir()
            meta = base / "home" / "workspaces" / "demo"
            meta.mkdir(parents=True)
            stale = meta / "app"
            stale.mkdir()
            (stale / "legacy.txt").write_text("x\n", encoding="utf-8")

            runtime = {
                "workspaces": [
                    {
                        "name": "demo",
                        "root": "/home/developer/workspaces/demo",
                        "meta_path": str(meta),
                        "projects": [
                            {
                                "name": "app",
                                "path": str(repo),
                                "workspace_path": "/home/developer/workspaces/demo/app",
                            }
                        ],
                    }
                ]
            }
            cfg = reconcile_host.host_cfg_from_runtime(runtime)
            templates = ROOT / "docker" / "rootfs" / "opt" / "cursor-defaults" / "templates" / "workspace"
            report = _reconcile.apply_workspaces(cfg, templates, base / "home" / "workspaces")

            self.assertTrue((meta / "app").is_symlink())
            self.assertEqual((meta / "app").resolve(), repo.resolve())
            self.assertEqual(len(report.workspaces[0].dirs_relocated), 1)


if __name__ == "__main__":
    unittest.main()
