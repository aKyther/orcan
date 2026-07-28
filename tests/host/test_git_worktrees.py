#!/usr/bin/env python3
"""Unit tests for git_worktrees.parse_porcelain / resolve helpers."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "repository"))

from git_worktrees import (  # noqa: E402
    default_worktree_path,
    parse_porcelain,
    resolve_worktree,
)


SAMPLE = """\
worktree /tmp/repo-main
HEAD abcdef0123456789
branch refs/heads/main

worktree /tmp/repo-feature-x
HEAD fedcba9876543210
branch refs/heads/feature-x

worktree /tmp/repo-detached
HEAD 1111222233334444
detached

"""


class ParsePorcelainTests(unittest.TestCase):
    def test_parses_branches_and_detached(self) -> None:
        trees = parse_porcelain(SAMPLE)
        self.assertEqual(len(trees), 3)
        self.assertEqual(trees[0].branch, "main")
        self.assertEqual(trees[0].path, Path("/tmp/repo-main").resolve())
        self.assertEqual(trees[1].branch, "feature-x")
        self.assertTrue(trees[2].detached)
        self.assertEqual(trees[2].branch, "")
        self.assertEqual(trees[2].label, "detached@1111222")


class DefaultPathTests(unittest.TestCase):
    def test_sibling_name(self) -> None:
        repo = Path("/home/u/code/api")
        self.assertEqual(
            default_worktree_path(repo, "feature/x"),
            Path("/home/u/code/api-feature-x").resolve(),
        )


class ResolveWithMockList(unittest.TestCase):
    def test_resolve_by_index_and_branch(self) -> None:
        trees = parse_porcelain(SAMPLE)

        # Patch list_worktrees via resolve's dependency — call matching logic inline
        # by temporarily monkeypatching.
        import git_worktrees as gw

        def fake_list(_repo: Path):
            return trees

        orig = gw.list_worktrees
        gw.list_worktrees = fake_list  # type: ignore[assignment]
        try:
            self.assertEqual(
                resolve_worktree(Path("/tmp"), "2").path,
                Path("/tmp/repo-feature-x").resolve(),
            )
            self.assertEqual(
                resolve_worktree(Path("/tmp"), "feature-x").path,
                Path("/tmp/repo-feature-x").resolve(),
            )
            self.assertEqual(
                resolve_worktree(Path("/tmp"), "repo-feature-x").path,
                Path("/tmp/repo-feature-x").resolve(),
            )
        finally:
            gw.list_worktrees = orig  # type: ignore[assignment]


class CreateIntegrationTests(unittest.TestCase):
    def test_create_and_list_real_repo(self) -> None:
        import subprocess

        from git_worktrees import create_worktree, list_worktrees

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "app"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "t@example.com"],
                cwd=repo,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "t"],
                cwd=repo,
                check=True,
                capture_output=True,
            )
            (repo / "README").write_text("x\n", encoding="utf-8")
            subprocess.run(["git", "add", "README"], cwd=repo, check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "init"],
                cwd=repo,
                check=True,
                capture_output=True,
            )
            wt = create_worktree(repo, branch="feature-demo")
            self.assertTrue(wt.path.is_dir())
            trees = list_worktrees(repo)
            self.assertGreaterEqual(len(trees), 2)
            names = {t.branch for t in trees}
            self.assertIn("feature-demo", names)

            # Same branch already checked out → recoverable error
            from git_worktrees import WorktreeCreateError, find_worktree_by_branch

            found = find_worktree_by_branch(repo, "feature-demo")
            self.assertIsNotNone(found)
            with self.assertRaises(WorktreeCreateError) as ctx:
                create_worktree(repo, branch="feature-demo", path=root / "dup", fatal=False)
            self.assertEqual(ctx.exception.code, "branch_in_use")
            self.assertIsNotNone(ctx.exception.existing)

            # Existing free branch (not checked out) still works via checkout attach —
            # create branch without worktree first.
            subprocess.run(
                ["git", "branch", "free-branch"],
                cwd=repo,
                check=True,
                capture_output=True,
            )
            wt2 = create_worktree(repo, branch="free-branch", path=root / "free-wt")
            self.assertEqual(wt2.branch, "free-branch")

    def test_managed_create_and_remove(self) -> None:
        import os
        import subprocess

        import git_worktrees as gw
        from managed_workspace import create_managed_workspace, remove_managed_workspace

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "orcan-data"
            home = root / "home"
            home.mkdir()
            os.environ["ORCAN_DATA"] = str(data)
            os.environ["ORCAN_HOME"] = str(home)

            def init_repo(name: str) -> Path:
                repo = root / name
                repo.mkdir()
                subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
                subprocess.run(
                    ["git", "config", "user.email", "t@example.com"],
                    cwd=repo,
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    ["git", "config", "user.name", "t"],
                    cwd=repo,
                    check=True,
                    capture_output=True,
                )
                (repo / "f").write_text("x\n", encoding="utf-8")
                subprocess.run(["git", "add", "f"], cwd=repo, check=True, capture_output=True)
                subprocess.run(
                    ["git", "commit", "-m", "i"],
                    cwd=repo,
                    check=True,
                    capture_output=True,
                )
                return repo

            api = init_repo("api")
            web = init_repo("web")
            cfg_path = home / "orcan.config.json"
            create_managed_workspace(
                config_path=cfg_path,
                workspace="feat-x",
                branch="feat-x",
                projects=[("backend", api), ("frontend", web)],
            )
            backend = data / "worktrees" / "feat-x" / "backend"
            frontend = data / "worktrees" / "feat-x" / "frontend"
            self.assertTrue(backend.is_dir())
            self.assertTrue(frontend.is_dir())
            self.assertTrue((data / "worktrees" / "manifest.json").is_file())
            remove_managed_workspace(config_path=cfg_path, workspace="feat-x", force=True)
            self.assertFalse(backend.exists())
            self.assertFalse(frontend.exists())
            cfg = __import__("json").loads(cfg_path.read_text(encoding="utf-8"))
            self.assertEqual(cfg.get("workspaces"), [])
            # cleanup env
            os.environ.pop("ORCAN_DATA", None)
            os.environ.pop("ORCAN_HOME", None)
            _ = gw


if __name__ == "__main__":
    unittest.main()
