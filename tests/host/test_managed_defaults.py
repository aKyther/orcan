#!/usr/bin/env python3
"""Managed image defaults update only while the user's copy is untouched."""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "docker/rootfs/usr/local/bin/docker-entrypoint"


class ManagedDefaultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"
        self.source = Path(self.temp.name) / "default"
        self.target = self.home / ".config/tool/config"
        self.home.mkdir()

    def seed(self, *legacy_hashes: str) -> None:
        script = '. "$1"; shift; seed_managed_default "$@"'
        subprocess.run(
            [
                "bash",
                "-c",
                script,
                "bash",
                str(ENTRYPOINT),
                str(self.source),
                str(self.target),
                "tool",
                *legacy_hashes,
            ],
            env={**os.environ, "HOME": str(self.home)},
            check=True,
        )

    def test_missing_target_is_seeded_and_future_default_refreshes(self) -> None:
        self.source.write_text("v1\n", encoding="utf-8")
        self.seed()
        self.assertEqual(self.target.read_text(encoding="utf-8"), "v1\n")
        self.source.write_text("v2\n", encoding="utf-8")
        self.seed()
        self.assertEqual(self.target.read_text(encoding="utf-8"), "v2\n")

    def test_user_edited_target_is_preserved(self) -> None:
        self.source.write_text("default\n", encoding="utf-8")
        self.target.parent.mkdir(parents=True)
        self.target.write_text("mine\n", encoding="utf-8")
        self.seed()
        self.assertEqual(self.target.read_text(encoding="utf-8"), "mine\n")

    def test_known_pre_sidecar_default_is_upgraded(self) -> None:
        old = b"old default\n"
        self.source.write_text("new default\n", encoding="utf-8")
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(old)
        self.seed(hashlib.sha256(old).hexdigest())
        self.assertEqual(self.target.read_text(encoding="utf-8"), "new default\n")


if __name__ == "__main__":
    unittest.main()
