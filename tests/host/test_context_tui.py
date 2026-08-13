#!/usr/bin/env python3
"""Tests for context_tui scan + non-interactive apply."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "repository"
_spec = importlib.util.spec_from_file_location("context_tui", SCRIPTS / "context_tui.py")
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def _git_init(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "t@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "t"],
        check=True,
    )
    (path / "README").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "README"], check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", "init"],
        check=True,
    )


class ScanReposTests(unittest.TestCase):
    def test_finds_child_repos_not_parent_when_many(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _git_init(root / "api")
            _git_init(root / "web")
            found = _mod.scan_repos(root)
            names = sorted(p.name for p in found)
            self.assertEqual(names, ["api", "web"])

    def test_nested_depth_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            group = root / "group"
            _git_init(group / "svc")
            found = _mod.scan_repos(root, max_depth=2)
            self.assertTrue(any(p.name == "svc" for p in found))


class ApplySelectionTests(unittest.TestCase):
    def test_mount_as_is(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            api = root / "api"
            web = root / "web"
            _git_init(api)
            _git_init(web)
            cfg_path = root / "orcan.config.json"
            _mod.apply_selection(
                config_path=cfg_path,
                workspace="acme",
                repos=[api, web],
                branch=None,
            )
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            ws = data["workspaces"][0]
            self.assertEqual(ws["name"], "acme")
            self.assertEqual(
                sorted(p["name"] for p in ws["projects"]),
                ["api", "web"],
            )
            self.assertEqual(
                {p["name"]: p["path"] for p in ws["projects"]}["api"],
                str(api.resolve()),
            )


if __name__ == "__main__":
    unittest.main()
