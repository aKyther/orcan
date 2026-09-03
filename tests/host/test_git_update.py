#!/usr/bin/env python3
"""Host tests for orcan update --to / downgrade helpers (cli/lib/git.sh)."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GIT_SH = ROOT / "cli" / "lib" / "git.sh"
LOG_SH = ROOT / "cli" / "lib" / "log.sh"
DEPS_SH = ROOT / "cli" / "lib" / "deps.sh"


def _bash(script: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    full = f"""
set -Eeuo pipefail
ORCAN_NO_COLOR=1
source '{LOG_SH}'
source '{DEPS_SH}'
source '{GIT_SH}'
orcan_log_init
{script}
"""
    merged = dict(os.environ)
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", "-c", full],
        text=True,
        capture_output=True,
        env=merged,
        check=False,
    )


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def _init_tagged_repo(path: Path, tags: list[str]) -> None:
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "test")
    (path / "VERSION").write_text("0.0.0\n", encoding="utf-8")
    _git(path, "add", "VERSION")
    _git(path, "commit", "-m", "init")
    for tag in tags:
        ver = tag.lstrip("v")
        (path / "VERSION").write_text(f"{ver}\n", encoding="utf-8")
        _git(path, "add", "VERSION")
        _git(path, "commit", "-m", f"release {tag}")
        _git(path, "tag", tag)
    # Self-origin so fetch --tags origin works offline.
    _git(path, "remote", "add", "origin", str(path))


class GitReleaseHelperTests(unittest.TestCase):
    def test_normalize_accepts_v_or_bare(self) -> None:
        r = _bash('orcan_git_normalize_release_tag 1.2.3; orcan_git_normalize_release_tag v9.0.1')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip().splitlines(), ["v1.2.3", "v9.0.1"])

    def test_normalize_rejects_junk(self) -> None:
        r = _bash('orcan_git_normalize_release_tag main')
        self.assertNotEqual(r.returncode, 0)

    def test_previous_and_checkout_to(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_tagged_repo(root, ["v0.1.0", "v0.2.0", "v0.3.0"])
            _git(root, "checkout", "--detach", "v0.3.0")
            env = {"ORCAN_ROOT": str(root), "ORCAN_DATA": str(root / "data")}
            r = _bash('orcan_git_previous_release_tag v0.3.0', env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.strip(), "v0.2.0")

            r = _bash('orcan_git_upgrade to 0.1.0', env=env)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            desc = subprocess.check_output(
                ["git", "-C", str(root), "describe", "--tags", "--exact-match"],
                text=True,
            ).strip()
            self.assertEqual(desc, "v0.1.0")

    def test_downgrade_one_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_tagged_repo(root, ["v0.1.0", "v0.2.0", "v0.3.0"])
            _git(root, "checkout", "--detach", "v0.3.0")
            env = {"ORCAN_ROOT": str(root), "ORCAN_DATA": str(root / "data")}
            r = _bash("orcan_git_downgrade", env=env)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            desc = subprocess.check_output(
                ["git", "-C", str(root), "describe", "--tags", "--exact-match"],
                text=True,
            ).strip()
            self.assertEqual(desc, "v0.2.0")

    def test_downgrade_refuses_newer_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_tagged_repo(root, ["v0.1.0", "v0.2.0", "v0.3.0"])
            _git(root, "checkout", "--detach", "v0.1.0")
            env = {"ORCAN_ROOT": str(root), "ORCAN_DATA": str(root / "data")}
            r = _bash("orcan_git_downgrade v0.3.0", env=env)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("newer", r.stderr)

    def test_downgrade_refuses_when_not_on_release_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_tagged_repo(root, ["v0.1.0", "v0.2.0"])
            # A detached commit without an exact release tag is ambiguous;
            # downgrade must require an explicit --to target instead.
            _git(root, "checkout", "--detach", "HEAD")
            (root / "VERSION").write_text("dev\n", encoding="utf-8")
            _git(root, "add", "VERSION")
            _git(root, "commit", "-m", "dev snapshot")
            env = {"ORCAN_ROOT": str(root), "ORCAN_DATA": str(root / "data")}
            r = _bash("orcan_git_downgrade", env=env)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("not on a release tag", r.stderr)

    def test_version_file_without_a_public_tag_is_not_a_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_tagged_repo(root, ["v0.1.0"])
            (root / "VERSION").write_text("9.9.9\n", encoding="utf-8")
            _git(root, "add", "VERSION")
            _git(root, "commit", "-m", "development version")
            env = {"ORCAN_ROOT": str(root), "ORCAN_DATA": str(root / "data")}
            r = _bash("orcan_git_local_release_tag", env=env)
            self.assertNotEqual(r.returncode, 0)
            self.assertEqual(r.stdout, "")

    def test_checkpoint_tag_is_not_a_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_tagged_repo(root, ["v0.1.0"])
            _git(root, "tag", "checkpoint/v0.2.0")
            env = {"ORCAN_ROOT": str(root), "ORCAN_DATA": str(root / "data")}
            r = _bash("orcan_git_latest_release_tag", env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.strip(), "v0.1.0")


class UpdateDowngradeCliTests(unittest.TestCase):
    def _cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(ROOT / "bin" / "orcan"), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            env={**os.environ, "ORCAN_NO_COLOR": "1"},
            check=False,
        )

    def test_help_documents_version_pin_commands(self) -> None:
        update = self._cli("update", "--help")
        upgrade = self._cli("upgrade", "--help")
        downgrade = self._cli("downgrade", "--help")
        self.assertEqual(update.returncode, 0, update.stderr)
        self.assertEqual(upgrade.returncode, 0, upgrade.stderr)
        self.assertEqual(downgrade.returncode, 0, downgrade.stderr)
        self.assertIn("Dev channel", update.stdout)
        self.assertIn("--to VERSION", upgrade.stdout)
        self.assertIn("upgrade", upgrade.stdout)
        self.assertIn("previous SemVer release", downgrade.stdout)

    def test_update_rejects_release_only_arguments(self) -> None:
        result = self._cli("update", "--main")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown argument", result.stderr)

    def test_downgrade_requires_version_after_to(self) -> None:
        result = self._cli("downgrade", "--to")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--to needs a version", result.stderr)


if __name__ == "__main__":
    unittest.main()
