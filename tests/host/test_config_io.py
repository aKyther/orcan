#!/usr/bin/env python3
"""Unit tests for scripts/repository/config_io.py (stdlib only)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "repository"))

import config_io  # noqa: E402


class ConfigIoTests(unittest.TestCase):
    def test_retargeted_alias_cannot_overwrite_a_different_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, second, alias = (
                Path(tmp) / name for name in ("one.json", "two.json", "alias.json")
            )
            first.write_text("{}\n")
            second.write_text('{"keep": true}\n')
            alias.symlink_to(first)
            snapshot = config_io.load_config(alias)
            alias.unlink()
            alias.symlink_to(second)
            with self.assertRaisesRegex(ValueError, "configuration path changed"):
                config_io.dump_config(alias, snapshot)
            self.assertEqual(config_io.load_config(second), {"keep": True})

    def test_absent_snapshot_and_copies_keep_revision_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            initial = config_io.load_config_or_create(path)
            stale = initial.copy()
            config_io.dump_config(path, initial)
            with self.assertRaisesRegex(ValueError, "configuration changed"):
                config_io.dump_config(path, stale)

    def test_loaded_snapshots_reject_lost_updates_and_can_save_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("{}\n")
            first = config_io.load_config(path)
            stale = config_io.load_config(path)
            first["one"] = True
            config_io.dump_config(path, first)
            first["two"] = True
            config_io.dump_config(path, first)
            stale["lost"] = True
            with self.assertRaisesRegex(ValueError, "configuration changed"):
                config_io.dump_config(path, stale)
            self.assertEqual(config_io.load_config(path), {"one": True, "two": True})

    def test_atomic_write_preserves_configuration_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target.json"
            target.write_text("{}\n")
            alias = Path(tmp) / "alias.json"
            alias.symlink_to(target)
            config_io.dump_config(alias, {"updated": True})
            self.assertTrue(alias.is_symlink())
            self.assertEqual(config_io.load_config(target), {"updated": True})

    def test_atomic_write_preserves_original_on_replace_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "orcan.config.json"
            path.write_text("{}\n")
            with patch.object(
                config_io.os, "replace", side_effect=OSError("disk error")
            ):
                with self.assertRaises(OSError):
                    config_io.dump_config(path, {"new": True})
            self.assertEqual(path.read_text(), "{}\n")
            self.assertEqual(list(Path(tmp).iterdir()), [path])

    def test_atomic_write_rejects_stale_snapshot_and_preserves_permissions(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "orcan.config.json"
            path.write_text("{}\n")
            path.chmod(0o640)
            with self.assertRaisesRegex(ValueError, "configuration changed"):
                config_io.dump_config(path, {"new": True}, expected=b"stale")
            config_io.dump_config(path, {"new": True}, expected=path.read_bytes())
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            self.assertEqual(list(Path(tmp).iterdir()), [path])

    def test_load_and_dump_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "orcan.config.json"
            data = {"workspaces": [{"name": "w", "projects": []}]}
            config_io.dump_config(path, data)
            loaded = config_io.load_config(path)
            self.assertEqual(loaded["workspaces"][0]["name"], "w")

    def test_discover_finds_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "orcan.config.json"
            path.write_text("{}\n", encoding="utf-8")
            self.assertEqual(config_io.discover_config(root), path)

    def test_discover_missing_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(config_io.discover_config(Path(tmp)))

    def test_yaml_leftover_dies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "orcan.config.yaml").write_text(
                "workspaces: []\n", encoding="utf-8"
            )
            with self.assertRaises(SystemExit):
                config_io.discover_config(root)

    def test_invalid_json_dies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "orcan.config.json"
            path.write_text("{not-json", encoding="utf-8")
            with self.assertRaises(SystemExit):
                config_io.load_config(path)

    def test_non_object_root_dies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "orcan.config.json"
            path.write_text("[]\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                config_io.load_config(path)

    def test_example_config_is_valid_json(self) -> None:
        example = ROOT / "orcan.config.example.json"
        data = json.loads(example.read_text(encoding="utf-8"))
        self.assertIn("workspaces", data)
        self.assertTrue(data["workspaces"])


if __name__ == "__main__":
    unittest.main()
