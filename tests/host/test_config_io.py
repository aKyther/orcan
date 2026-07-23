#!/usr/bin/env python3
"""Unit tests for scripts/repository/config_io.py (stdlib only)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "repository"))

import config_io  # noqa: E402


class ConfigIoTests(unittest.TestCase):
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
            (root / "orcan.config.yaml").write_text("workspaces: []\n", encoding="utf-8")
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
