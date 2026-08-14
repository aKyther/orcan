#!/usr/bin/env python3
"""Tests for context_tui scan + non-interactive apply."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


class ScanDirsTests(unittest.TestCase):
    def test_includes_plain_dirs_tagged_as_non_git(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _git_init(root / "api")
            (root / "notes").mkdir()
            found = {p.name: is_git for p, is_git in _mod.scan_dirs(root)}
            self.assertEqual(found, {"api": True, "notes": False})

    def test_plain_child_still_recursed_into_for_grandchildren(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            group = root / "group"
            _git_init(group / "svc")
            (group / "docs").mkdir()
            found = {p.name: is_git for p, is_git in _mod.scan_dirs(root, max_depth=2)}
            self.assertEqual(found.get("group"), False)
            self.assertEqual(found.get("svc"), True)
            self.assertEqual(found.get("docs"), False)


class ListSubdirsTests(unittest.TestCase):
    def test_lists_dirs_sorted_and_skips_hidden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "b").mkdir()
            (root / "a").mkdir()
            (root / ".hidden").mkdir()
            (root / "file.txt").write_text("x", encoding="utf-8")
            found = _mod.list_subdirs(root)
            self.assertEqual([p.name for p in found], ["a", "b"])

    def test_missing_dir_returns_empty(self) -> None:
        found = _mod.list_subdirs(Path("/no/such/directory"))
        self.assertEqual(found, [])


class HumanizeTests(unittest.TestCase):
    def test_seconds_minutes_hours_days(self) -> None:
        self.assertEqual(_mod._humanize(30), "30s")
        self.assertEqual(_mod._humanize(90), "1m")
        self.assertEqual(_mod._humanize(3600), "1h")
        self.assertEqual(_mod._humanize(2 * 86400), "2d")

    def test_negative_clamps_to_zero(self) -> None:
        self.assertEqual(_mod._humanize(-5), "0s")


class UpdateParentHistoryTests(unittest.TestCase):
    def test_pushes_new_parent_to_front_with_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a"
            b = root / "b"
            a.mkdir()
            b.mkdir()
            hist = _mod.update_parent_history(
                [{"path": str(b), "ts": 100.0}], a, now=200.0
            )
            self.assertEqual([h["path"] for h in hist], [str(a), str(b)])
            self.assertEqual(hist[0]["ts"], 200.0)

    def test_moves_existing_entry_to_front_without_duplicating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a"
            b = root / "b"
            a.mkdir()
            b.mkdir()
            hist = _mod.update_parent_history(
                [{"path": str(a), "ts": 100.0}, {"path": str(b), "ts": 90.0}],
                b,
                now=200.0,
            )
            self.assertEqual([h["path"] for h in hist], [str(b), str(a)])

    def test_drops_entries_that_no_longer_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a"
            a.mkdir()
            hist = _mod.update_parent_history(
                [{"path": str(root / "gone"), "ts": 100.0}], a, now=200.0
            )
            self.assertEqual([h["path"] for h in hist], [str(a)])

    def test_drops_entries_past_ttl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a"
            b = root / "b"
            a.mkdir()
            b.mkdir()
            now = 10 * 86400.0
            stale_ts = now - 4 * 86400  # older than 3-day TTL
            fresh_ts = now - 1 * 86400
            hist = _mod.update_parent_history(
                [{"path": str(b), "ts": stale_ts}],
                a,
                now=now,
                ttl_days=3.0,
            )
            self.assertEqual([h["path"] for h in hist], [str(a)])

            hist2 = _mod.update_parent_history(
                [{"path": str(b), "ts": fresh_ts}],
                a,
                now=now,
                ttl_days=3.0,
            )
            self.assertEqual([h["path"] for h in hist2], [str(a), str(b)])

    def test_respects_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dirs = []
            for i in range(5):
                d = root / f"d{i}"
                d.mkdir()
                dirs.append(d)
            hist = [{"path": str(d), "ts": 100.0} for d in dirs[:4]]
            newest = root / "newest"
            newest.mkdir()
            result = _mod.update_parent_history(hist, newest, limit=3, now=200.0)
            self.assertEqual(len(result), 3)
            self.assertEqual(result[0]["path"], str(newest))


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


class ManageRowsTests(unittest.TestCase):
    """manage_rows/manage_* are curses-free by design so the "manage existing
    config" screen's mutation logic is directly unit-testable."""

    def test_flattens_workspace_headers_and_project_rows(self) -> None:
        workspaces = [
            {"name": "acme", "projects": [{"name": "api", "path": "/x/api"}]},
            {"name": "other", "projects": []},
        ]
        rows = _mod.manage_rows(workspaces)
        self.assertEqual(
            rows,
            [("ws", 0, None), ("proj", 0, 0), ("ws", 1, None)],
        )


class ManageRenameTests(unittest.TestCase):
    def test_rename_workspace_success(self) -> None:
        workspaces = [{"name": "acme", "projects": []}]
        err = _mod.manage_rename_workspace(workspaces, 0, "acme2")
        self.assertIsNone(err)
        self.assertEqual(workspaces[0]["name"], "acme2")

    def test_rename_workspace_rejects_duplicate(self) -> None:
        workspaces = [{"name": "acme", "projects": []}, {"name": "other", "projects": []}]
        err = _mod.manage_rename_workspace(workspaces, 1, "acme")
        self.assertEqual(err, "workspace 'acme' already exists")
        self.assertEqual(workspaces[1]["name"], "other")

    def test_rename_workspace_rejects_invalid_name(self) -> None:
        workspaces = [{"name": "acme", "projects": []}]
        err = _mod.manage_rename_workspace(workspaces, 0, "bad name!")
        self.assertEqual(err, "invalid workspace name")

    def test_rename_project_rejects_duplicate_within_workspace(self) -> None:
        ws = {
            "name": "acme",
            "projects": [{"name": "api", "path": "/x"}, {"name": "web", "path": "/y"}],
        }
        err = _mod.manage_rename_project(ws, 1, "api")
        self.assertEqual(err, "project 'api' already in this workspace")

    def test_rename_project_success(self) -> None:
        ws = {"name": "acme", "projects": [{"name": "api", "path": "/x"}]}
        err = _mod.manage_rename_project(ws, 0, "api2")
        self.assertIsNone(err)
        self.assertEqual(ws["projects"][0]["name"], "api2")


class ManageChangePathTests(unittest.TestCase):
    def test_accepts_existing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = {"name": "acme", "projects": [{"name": "api", "path": "/old"}]}
            err = _mod.manage_change_project_path(ws, 0, tmp)
            self.assertIsNone(err)
            self.assertEqual(ws["projects"][0]["path"], str(Path(tmp).resolve()))

    def test_rejects_nonexistent_path(self) -> None:
        ws = {"name": "acme", "projects": [{"name": "api", "path": "/old"}]}
        err = _mod.manage_change_project_path(ws, 0, "/no/such/directory")
        self.assertIsNotNone(err)
        self.assertEqual(ws["projects"][0]["path"], "/old")

    def test_rejects_relative_path(self) -> None:
        ws = {"name": "acme", "projects": [{"name": "api", "path": "/old"}]}
        err = _mod.manage_change_project_path(ws, 0, "relative/dir")
        self.assertIsNotNone(err)


class ManageDeleteTests(unittest.TestCase):
    def test_delete_project_removes_and_returns_it(self) -> None:
        ws = {
            "name": "acme",
            "projects": [{"name": "api", "path": "/x"}, {"name": "web", "path": "/y"}],
        }
        deleted = _mod.manage_delete_project(ws, 0)
        self.assertEqual(deleted["name"], "api")
        self.assertEqual([p["name"] for p in ws["projects"]], ["web"])

    def test_delete_workspace_removes_and_returns_it(self) -> None:
        workspaces = [{"name": "acme", "projects": []}, {"name": "other", "projects": []}]
        deleted = _mod.manage_delete_workspace(workspaces, 0)
        self.assertEqual(deleted["name"], "acme")
        self.assertEqual([ws["name"] for ws in workspaces], ["other"])


class ManagedProjectsTests(unittest.TestCase):
    def test_filters_to_paths_under_managed_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"ORCAN_DATA": tmp}):
                managed_dir = Path(tmp) / "worktrees" / "acme" / "api"
                managed_dir.mkdir(parents=True)
                other_dir = Path(tmp) / "elsewhere"
                other_dir.mkdir()
                ws = {
                    "name": "acme",
                    "projects": [
                        {"name": "api", "path": str(managed_dir)},
                        {"name": "web", "path": str(other_dir)},
                    ],
                }
                result = _mod.managed_projects(ws)
                self.assertEqual([p["name"] for p in result], ["api"])

    def test_no_projects_is_empty(self) -> None:
        self.assertEqual(_mod.managed_projects({"name": "acme", "projects": []}), [])


if __name__ == "__main__":
    unittest.main()
