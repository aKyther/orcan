#!/usr/bin/env python3
"""Regression tests for the checkpoint/release CHANGELOG.md surgery in
release.sh, run against a throwaway git repo — never the real checkout.

Model under test:
  - `checkpoint` (make tag): a frequent SemVer stop, fully pushed (commit
    + tag). Its tag lives under checkpoint/vX.Y.Z, not bare vX.Y.Z, so it
    can never be picked up by orcan update/downgrade (cli/lib/git.sh) or
    fire .github/workflows/release.yml's "v*.*.*" tag-push trigger.
  - `release` (make release): rare, deliberate, pushes a bare vX.Y.Z;
    drops a CalVer divider grouping every checkpoint since the previous
    one.

UpdateHintSafetyTests exercises the *actual* cli/lib/git.sh functions
(not a reimplementation) against a fixture with both tag kinds pushed,
so drift between release.sh and cli/lib/git.sh gets caught here.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RELEASE_SH = ROOT / "scripts" / "repository" / "release.sh"
GIT_LIB_SH = ROOT / "cli" / "lib" / "git.sh"


def run(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise AssertionError(f"{args} failed:\n{proc.stdout}\n{proc.stderr}")
    return proc


class ReleaseFixture:
    """A minimal repo skeleton release.sh can operate on."""

    def __init__(self, tmp: Path) -> None:
        self.root = tmp
        (self.root / "scripts" / "repository").mkdir(parents=True)
        (self.root / "cockpit").mkdir()
        (self.root / "docs" / "en").mkdir(parents=True)
        (self.root / "docs" / "pl").mkdir(parents=True)

        shutil.copy(RELEASE_SH, self.root / "scripts" / "repository" / "release.sh")
        (self.root / "cockpit" / "pyproject.toml").write_text('version = "3.0.5"\n')
        (self.root / "cockpit" / "uv.lock").write_text('name = "orcan-cockpit"\nversion = "3.0.5"\n')
        (self.root / "VERSION").write_text("3.0.5\n")
        (self.root / "mkdocs.yml").write_text('orcan_version: "3.0.5"\n')
        (self.root / "README.md").write_text("Version **3.0.5**\n")
        (self.root / "docs" / "en" / "index.md").write_text("Version **3.0.5**\n")
        (self.root / "docs" / "pl" / "index.md").write_text("Wersja **3.0.5**\n")
        (self.root / "CHANGELOG.md").write_text(
            "# Changelog\n\n## [Unreleased]\n\n## [3.0.5] - 2026-08-27\n\n### Fixed\n\n- prior fix\n"
        )

        run(["git", "init", "-q"], cwd=self.root)
        run(["git", "config", "user.email", "test@test.local"], cwd=self.root)
        run(["git", "config", "user.name", "Test"], cwd=self.root)
        run(["git", "add", "-A"], cwd=self.root)
        run(["git", "commit", "-q", "-m", "init"], cwd=self.root)
        run(["git", "init", "-q", "--bare", "../origin.git"], cwd=self.root)
        run(["git", "remote", "add", "origin", "../origin.git"], cwd=self.root)
        run(["git", "branch", "-M", "main"], cwd=self.root)
        run(["git", "push", "-q", "-u", "origin", "main"], cwd=self.root)

    def sh(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return run(["bash", "./scripts/repository/release.sh", *args], cwd=self.root, check=check)

    def add_unreleased(self, heading: str, bullet: str) -> None:
        p = self.root / "CHANGELOG.md"
        p.write_text(p.read_text().replace(
            "## [Unreleased]\n", f"## [Unreleased]\n\n### {heading}\n\n- {bullet}\n", 1
        ))
        run(["git", "add", "CHANGELOG.md"], cwd=self.root)
        run(["git", "commit", "-q", "-m", f"chore: {bullet}"], cwd=self.root)

    def changelog(self) -> str:
        return (self.root / "CHANGELOG.md").read_text()

    def tags(self) -> list[str]:
        return run(["git", "tag", "-l"], cwd=self.root).stdout.split()

    def remote_tags(self) -> list[str]:
        out = run(["git", "ls-remote", "--tags", "origin"], cwd=self.root).stdout
        return [line.split("refs/tags/")[1] for line in out.splitlines() if "refs/tags/" in line]

    def remote_head(self) -> str:
        return run(["git", "ls-remote", "origin", "main"], cwd=self.root).stdout.split()[0]

    def local_head(self) -> str:
        return run(["git", "rev-parse", "HEAD"], cwd=self.root).stdout.strip()

    def cli_git_fn(self, fn: str) -> str:
        """Call an actual cli/lib/git.sh function against this fixture."""
        proc = run(
            ["bash", "-c", f'source "{GIT_LIB_SH}" && ORCAN_ROOT="{self.root}" {fn}'],
            cwd=self.root,
            check=False,
        )
        return proc.stdout.strip()

    def is_clean(self) -> bool:
        return run(["git", "status", "--porcelain"], cwd=self.root).stdout == ""


class CheckpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.fx = ReleaseFixture(Path(self._tmp.name) / "repo")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_checkpoint_needs_content(self) -> None:
        proc = self.fx.sh("checkpoint", "patch", check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("nothing to checkpoint", proc.stderr)
        # A checkpoint that dies on validation must leave zero residue —
        # regression: this used to bump/write version files (and leave
        # them uncommitted) *before* checking Unreleased had content.
        self.assertEqual(self.fx.sh("print").stdout.strip(), "3.0.5")
        self.assertTrue(self.fx.is_clean(), "checkpoint left the tree dirty after failing")

    def test_checkpoint_bumps_cuts_and_pushes_under_checkpoint_namespace(self) -> None:
        self.fx.add_unreleased("Fixed", "a real fix")
        self.fx.sh("checkpoint", "patch")

        self.assertEqual(self.fx.sh("print").stdout.strip(), "3.0.6")
        self.assertIn("checkpoint/v3.0.6", self.fx.tags())
        # Fully pushed — commit AND tag reach origin (nothing local-only)...
        self.assertIn("checkpoint/v3.0.6", self.fx.remote_tags())
        self.assertEqual(self.fx.remote_head(), self.fx.local_head())
        # ...but never as a bare vX.Y.Z — that's what keeps it invisible
        # to orcan update/downgrade and release.yml's tag-push trigger.
        self.assertNotIn("v3.0.6", self.fx.remote_tags())

        changelog = self.fx.changelog()
        self.assertIn("## [Unreleased]\n\n## [3.0.6] - ", changelog)
        self.assertIn("a real fix", changelog)

    def test_second_checkpoint_without_new_content_fails(self) -> None:
        self.fx.add_unreleased("Fixed", "first fix")
        self.fx.sh("checkpoint", "patch")
        proc = self.fx.sh("checkpoint", "patch", check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("nothing to checkpoint", proc.stderr)


class ReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.fx = ReleaseFixture(Path(self._tmp.name) / "repo")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_release_auto_checkpoints_and_pushes(self) -> None:
        self.fx.add_unreleased("Fixed", "shipped fix")
        proc = self.fx.sh("release", "26.9")
        self.assertIn("Released 26.9 → v3.0.6", proc.stdout)
        # Release ships both a real SemVer tag and its own CalVer tag —
        # two pointers at the same commit, both on origin.
        self.assertIn("v3.0.6", self.fx.remote_tags())
        self.assertIn("26.9", self.fx.remote_tags())

        changelog = self.fx.changelog()
        self.assertIn("## [Unreleased]\n\n## 26.9 — ", changelog)
        self.assertIn("## [3.0.6] - ", changelog)

    def test_release_groups_multiple_checkpoints_under_one_divider(self) -> None:
        self.fx.add_unreleased("Fixed", "fix one")
        self.fx.sh("checkpoint", "patch")
        self.fx.add_unreleased("Added", "feature one")
        self.fx.sh("checkpoint", "minor")
        self.fx.sh("release", "26.9")

        changelog = self.fx.changelog()
        divider = changelog.index("## 26.9")
        v106 = changelog.index("## [3.0.6]")
        v110 = changelog.index("## [3.1.0]")
        # Both checkpoints sit below the single release divider.
        self.assertLess(divider, v106)
        self.assertLess(divider, v110)
        # Only the release-time bare tag (v3.1.0, + the 26.9 CalVer tag)
        # is pushed as a real release; the earlier checkpoint still shows
        # up, but only under its checkpoint/ namespace.
        self.assertIn("v3.1.0", self.fx.remote_tags())
        self.assertIn("26.9", self.fx.remote_tags())
        self.assertNotIn("v3.0.6", self.fx.remote_tags())
        self.assertIn("checkpoint/v3.0.6", self.fx.remote_tags())

    def test_release_label_must_look_like_calver(self) -> None:
        self.fx.add_unreleased("Fixed", "a fix")
        proc = self.fx.sh("release", "not-a-calver", check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("release label must look like YY.Q", proc.stderr)

    def test_release_ensures_semver_tag_if_no_prior_checkpoint(self) -> None:
        # Releasing straight off accumulated Unreleased content, with no
        # preceding `make tag`, must still end up with a real vX.Y.Z tag.
        self.fx.add_unreleased("Fixed", "never checkpointed")
        self.fx.sh("release", "26.9")
        self.assertIn("v3.0.6", self.fx.tags())
        self.assertIn("v3.0.6", self.fx.remote_tags())

    def test_release_refuses_to_reuse_a_calver_label(self) -> None:
        self.fx.add_unreleased("Fixed", "first release")
        self.fx.sh("release", "26.9")
        self.fx.add_unreleased("Fixed", "second release")
        head_before = self.fx.local_head()
        proc = self.fx.sh("release", "26.9", check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("already exists", proc.stderr)
        # Regression: this used to auto-checkpoint + commit the CHANGELOG
        # divider + tag vX.Y.Z *before* discovering the label collision,
        # leaving a half-finished release (extra local commit/tag) behind.
        self.assertEqual(self.fx.local_head(), head_before, "release left an extra commit behind")
        self.assertTrue(self.fx.is_clean(), "release left the tree dirty after failing")


class UpdateHintSafetyTests(unittest.TestCase):
    """Exercises the real cli/lib/git.sh functions, not a reimplementation
    — proves checkpoint/CalVer tags can never surface as an orcan
    update/downgrade target, only a real release's bare vX.Y.Z can."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.fx = ReleaseFixture(Path(self._tmp.name) / "repo")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_checkpoints_and_calver_tag_invisible_to_update_targeting(self) -> None:
        self.fx.add_unreleased("Fixed", "fix one")
        self.fx.sh("checkpoint", "patch")  # checkpoint/v3.0.6
        self.fx.add_unreleased("Added", "feature one")
        self.fx.sh("release", "26.9")  # auto-checkpoints (patch) -> v3.0.7 + 26.9

        self.assertEqual(self.fx.cli_git_fn("orcan_git_latest_release_tag"), "v3.0.7")
        self.assertEqual(self.fx.cli_git_fn("orcan_git_remote_latest_release_tag"), "v3.0.7")

    def test_a_deliberately_higher_checkpoint_still_loses(self) -> None:
        # Even a checkpoint numbered far above any real release must
        # never outrank it — the namespace, not the version number, is
        # what update targeting keys off.
        self.fx.add_unreleased("Fixed", "a fix")
        self.fx.sh("release", "26.9")  # v3.0.6
        run(["git", "tag", "-a", "checkpoint/v9.9.9", "-m", "high checkpoint"], cwd=self.fx.root)
        run(["git", "push", "-q", "origin", "checkpoint/v9.9.9"], cwd=self.fx.root)

        self.assertEqual(self.fx.cli_git_fn("orcan_git_remote_latest_release_tag"), "v3.0.6")


if __name__ == "__main__":
    unittest.main()
