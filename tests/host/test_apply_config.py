#!/usr/bin/env python3
"""Unit tests for apply-config helpers and a tempfile e2e apply."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "repository"
sys.path.insert(0, str(SCRIPTS))

_spec = importlib.util.spec_from_file_location(
    "apply_config", SCRIPTS / "apply-config.py"
)
assert _spec and _spec.loader
apply_config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(apply_config)


class FormatEnvTests(unittest.TestCase):
    def test_plain(self) -> None:
        self.assertEqual(apply_config.format_env_value("8"), "8")

    def test_spaces_quoted(self) -> None:
        self.assertTrue(apply_config.format_env_value("a b").startswith('"'))


class NormalizeWorkspacesTests(unittest.TestCase):
    def test_workspaces_array(self) -> None:
        raw = apply_config.normalize_workspaces_raw(
            {
                "workspaces": [
                    {
                        "name": "app",
                        "projects": [{"name": "p", "path": "/tmp"}],
                    }
                ]
            }
        )
        self.assertEqual(len(raw), 1)
        self.assertEqual(raw[0]["name"], "app")

    def test_rejects_projects_dir(self) -> None:
        with self.assertRaises(SystemExit):
            apply_config.normalize_workspaces_raw({"projects_dir": "/x"})

    def test_empty_workspaces_dies(self) -> None:
        with self.assertRaises(SystemExit):
            apply_config.normalize_workspaces_raw({"workspaces": []})


class EnsureEnvKeyTests(unittest.TestCase):
    def test_set_and_preserve(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text("CPUS=4\n", encoding="utf-8")
            apply_config.ensure_env_key(env, "MEMORY", "16g")
            apply_config.ensure_env_key_unless_set(env, "CPUS", "99")
            text = env.read_text(encoding="utf-8")
            self.assertIn("MEMORY=16g", text)
            self.assertIn("CPUS=4", text)
            self.assertNotIn("CPUS=99", text)


class ApplyConfigE2ETests(unittest.TestCase):
    def test_apply_writes_runtime_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proj = root / "proj"
            proj.mkdir()
            (root / ".env.example").write_text(
                "USER_UID=1000\nUSER_GID=1000\n", encoding="utf-8"
            )
            cfg = {
                "workspaces": [
                    {
                        "name": "demo",
                        "projects": [
                            {"name": "app", "path": str(proj.resolve())},
                        ],
                    }
                ],
                "tmux": {"initial_windows": 2, "window_prefix": "tab"},
                "ttyd": {
                    "port": 7681,
                    "host_port": 7681,
                    "font_size": 22,
                    "font_family": "monospace",
                    "theme": "dark",
                },
                "resources": {
                    "cpus": 2,
                    "memory": "4g",
                    "shm_size": "1g",
                    "tmpfs_size": "1g",
                },
            }
            (root / "orcan.config.json").write_text(
                json.dumps(cfg, indent=2) + "\n", encoding="utf-8"
            )

            # Invoke main with argv
            old_argv = sys.argv
            try:
                sys.argv = [
                    "apply-config.py",
                    "--root",
                    str(root),
                    "--config",
                    str(root / "orcan.config.json"),
                ]
                apply_config.main()
            finally:
                sys.argv = old_argv

            runtime = root / ".orcan" / "runtime-config.json"
            compose = root / ".orcan" / "compose-projects.generated.yml"
            manifest = root / ".orcan" / "workspace.manifest.json"
            env = root / ".env"

            self.assertTrue(runtime.is_file())
            self.assertTrue(compose.is_file())
            self.assertTrue(manifest.is_file())
            self.assertTrue(env.is_file())

            runtime_data = json.loads(runtime.read_text(encoding="utf-8"))
            self.assertEqual(runtime_data["workspaces"][0]["name"], "demo")

            compose_text = compose.read_text(encoding="utf-8")
            self.assertIn(str(proj.resolve()), compose_text)

            env_text = env.read_text(encoding="utf-8")
            self.assertIn("WORKSPACE_NAME=demo", env_text)
            self.assertIn("ORCAN_COMPOSE_PROJECTS=", env_text)


if __name__ == "__main__":
    unittest.main()
