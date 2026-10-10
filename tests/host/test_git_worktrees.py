"""Unit tests for git_worktrees.parse_porcelain / resolve helpers."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "repository"))

from git_worktrees import (
    ManifestEntry,
    default_worktree_path,
    load_manifest,
    manifest_upsert,
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


class ManifestTests(unittest.TestCase):
    def test_keeps_multiple_branches_of_one_repo_in_one_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sandbox"
            with patch.dict("os.environ", {"ORCAN_PROJECTS_ROOT": str(root)}):
                manifest_upsert(
                    ManifestEntry(
                        workspace="platform",
                        project="api--feature-auth",
                        repo="/source/api",
                        path=str(root / ".worktrees/platform/api--feature-auth"),
                        branch="feature/auth",
                    )
                )
                manifest_upsert(
                    ManifestEntry(
                        workspace="platform",
                        project="api--fix-cache",
                        repo="/source/api",
                        path=str(root / ".worktrees/platform/api--fix-cache"),
                        branch="fix/cache",
                    )
                )

                entries = load_manifest()

        self.assertEqual(
            [entry.project for entry in entries],
            ["api--feature-auth", "api--fix-cache"],
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
