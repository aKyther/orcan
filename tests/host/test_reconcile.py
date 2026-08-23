#!/usr/bin/env python3
"""Unit tests for the in-container reconcile module (orcan.reconcile).

Same function container boot (init-workspace) and on-demand runtime
modification (orcan-runtime-reconcile) both call — tested here purely as a
filesystem transform, independent of Docker/tmux.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "docker" / "rootfs" / "usr" / "local" / "lib"

# Loaded by file path (not "orcan.reconcile" on sys.path) so this doesn't
# collide with workspaces/orcan/ in this very checkout — a synced workspace
# happens to be named "orcan" and would otherwise shadow the real package.
_spec = importlib.util.spec_from_file_location(
    "orcan_reconcile_module", LIB / "orcan" / "reconcile.py"
)
assert _spec and _spec.loader
_reconcile = importlib.util.module_from_spec(_spec)
# Dataclasses (with `from __future__ import annotations`) resolve field
# types via sys.modules[cls.__module__] — must be registered before exec.
sys.modules[_spec.name] = _reconcile
_spec.loader.exec_module(_reconcile)
apply_workspaces = _reconcile.apply_workspaces


def _cfg(workspaces: list[dict]) -> dict:
    return {"workspaces": workspaces}


def _ws(name: str, root: Path, projects: list[dict]) -> dict:
    return {
        "name": name,
        "root": str(root),
        "tmux_session": name,
        "projects": projects,
    }


def _project(name: str, path: Path, workspace_path: Path) -> dict:
    return {
        "name": name,
        "path": str(path),
        "workspace_path": str(workspace_path),
        "container_path": str(path),
    }


class ApplyWorkspacesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.defaults_root = self.tmp / "templates" / "workspace"
        self.defaults_root.mkdir(parents=True)

        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.workspaces_parent = self.tmp / "workspaces"
        self.ws_root = self.workspaces_parent / "demo"

    def _apply(self, cfg: dict):
        return apply_workspaces(cfg, self.defaults_root, self.workspaces_parent)

    def test_creates_symlink_manifest_and_agents_md(self) -> None:
        cfg = _cfg(
            [
                _ws(
                    "demo",
                    self.ws_root,
                    [_project("app", self.repo, self.ws_root / "app")],
                )
            ]
        )

        report = self._apply(cfg)

        self.assertEqual(report.total_repos(), 1)
        self.assertTrue((self.ws_root / "app").is_symlink())
        self.assertEqual((self.ws_root / "app").resolve(), self.repo.resolve())
        self.assertTrue((self.ws_root / ".manifest.json").is_file())
        self.assertTrue((self.ws_root / "AGENTS.md").is_file())
        self.assertTrue((self.ws_root / "CLAUDE.md").is_file())
        self.assertEqual(report.workspaces[0].symlinks_created, [str(self.ws_root / "app")])

    def test_second_run_with_no_change_is_a_no_op(self) -> None:
        cfg = _cfg(
            [
                _ws(
                    "demo",
                    self.ws_root,
                    [_project("app", self.repo, self.ws_root / "app")],
                )
            ]
        )
        self._apply(cfg)
        agents_md_before = (self.ws_root / "AGENTS.md").stat().st_mtime_ns

        report2 = self._apply(cfg)

        self.assertEqual(report2.workspaces[0].symlinks_created, [])
        self.assertEqual(report2.workspaces[0].symlinks_removed, [])
        self.assertFalse(report2.changed())
        # AGENTS.md is regenerated content (cheap, deterministic) — still
        # written every run, but the symlink itself was left untouched.
        self.assertTrue((self.ws_root / "AGENTS.md").stat().st_mtime_ns >= agents_md_before)

    def test_removing_project_drops_orphan_symlink(self) -> None:
        cfg_with = _cfg(
            [
                _ws(
                    "demo",
                    self.ws_root,
                    [_project("app", self.repo, self.ws_root / "app")],
                )
            ]
        )
        self._apply(cfg_with)
        self.assertTrue((self.ws_root / "app").is_symlink())

        cfg_without = _cfg([_ws("demo", self.ws_root, [])])
        report = self._apply(cfg_without)

        self.assertFalse((self.ws_root / "app").exists())
        self.assertEqual(report.workspaces[0].symlinks_removed, [str(self.ws_root / "app")])

    def test_removing_the_only_workspace_prunes_its_stale_dir(self) -> None:
        cfg_with = _cfg(
            [
                _ws(
                    "demo",
                    self.ws_root,
                    [_project("app", self.repo, self.ws_root / "app")],
                )
            ]
        )
        self._apply(cfg_with)
        self.assertTrue(self.ws_root.is_dir())

        # Config always keeps >=1 workspace in practice (apply-config.py
        # rejects an empty workspaces[]); "demo" here stands in for whatever
        # the one remaining workspace is — the point under test is that
        # pruning scans the fixed workspaces-parent directly, not just
        # parents derived from the surviving list, so a *sole* removed
        # workspace still gets cleaned up.
        other_root = self.workspaces_parent / "other"
        report = self._apply(_cfg([_ws("other", other_root, [])]))

        self.assertFalse(self.ws_root.exists())
        self.assertTrue(other_root.exists())
        self.assertEqual(report.stale_workspace_dirs_removed, [str(self.ws_root)])

    def test_adding_a_second_project_only_adds_that_symlink(self) -> None:
        cfg1 = _cfg(
            [
                _ws(
                    "demo",
                    self.ws_root,
                    [_project("app", self.repo, self.ws_root / "app")],
                )
            ]
        )
        self._apply(cfg1)

        repo2 = self.tmp / "repo2"
        repo2.mkdir()
        cfg2 = _cfg(
            [
                _ws(
                    "demo",
                    self.ws_root,
                    [
                        _project("app", self.repo, self.ws_root / "app"),
                        _project("app2", repo2, self.ws_root / "app2"),
                    ],
                )
            ]
        )
        report = self._apply(cfg2)

        self.assertEqual(report.workspaces[0].symlinks_created, [str(self.ws_root / "app2")])
        self.assertTrue((self.ws_root / "app").is_symlink())
        self.assertTrue((self.ws_root / "app2").is_symlink())

    def test_disabled_workspace_is_skipped(self) -> None:
        cfg = _cfg(
            [
                {
                    "name": "demo",
                    "root": str(self.ws_root),
                    "enabled": False,
                    "projects": [],
                }
            ]
        )
        report = self._apply(cfg)
        self.assertEqual(report.workspaces, [])
        self.assertFalse(self.ws_root.exists())


if __name__ == "__main__":
    unittest.main()
