#!/usr/bin/env python3
"""Safety contract for `orcan uninstall --purge-data`."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "repository"))
SPEC = importlib.util.spec_from_file_location(
    "uninstall_data", ROOT / "scripts" / "repository" / "uninstall_data.py"
)
assert SPEC is not None and SPEC.loader is not None
uninstall_data = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(uninstall_data)


class PurgeTargetsTests(unittest.TestCase):
    def test_default_nested_sandbox_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "orcan"
            repo = data / "sandbox" / "app"
            repo.mkdir(parents=True)
            (repo / "README.md").write_text("keep\n", encoding="utf-8")
            (data / "cache").mkdir()
            (data / "cache" / "blob").write_text("drop\n", encoding="utf-8")
            (data / "orcan.config.json").write_text("{}\n", encoding="utf-8")

            kept = uninstall_data.purge_targets([data], [data / "sandbox"])

            self.assertEqual(kept, [(data / "sandbox").resolve()])
            self.assertEqual((repo / "README.md").read_text(encoding="utf-8"), "keep\n")
            self.assertFalse((data / "cache").exists())
            self.assertFalse((data / "orcan.config.json").exists())

    def test_external_projects_root_survives_full_data_removal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            data = base / "orcan-data"
            projects = base / "projects"
            data.mkdir()
            projects.mkdir()
            (data / "cache").write_text("drop\n", encoding="utf-8")
            (projects / "repo").write_text("keep\n", encoding="utf-8")

            uninstall_data.purge_targets([data], [projects])

            self.assertFalse(data.exists())
            self.assertTrue((projects / "repo").is_file())

    def test_projects_root_equal_to_data_preserves_everything(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "all-projects"
            data.mkdir()
            (data / "repo").write_text("keep\n", encoding="utf-8")

            uninstall_data.purge_targets([data], [data])

            self.assertTrue((data / "repo").is_file())

    def test_configured_project_inside_data_is_also_protected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            project = data / "legacy-project"
            project.mkdir(parents=True)
            (project / ".git").mkdir()
            config = Path(tmp) / "orcan.config.json"
            config.write_text(
                json.dumps(
                    {
                        "workspaces": [
                            {"projects": [{"name": "legacy", "path": str(project)}]}
                        ]
                    }
                ),
                encoding="utf-8",
            )

            protected = uninstall_data.configured_project_paths(config)
            uninstall_data.purge_targets([data], protected)

            self.assertTrue((project / ".git").is_dir())

    def test_malformed_config_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "orcan.config.json"
            config.write_text("{broken", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                uninstall_data.configured_project_paths(config)

    def test_symlink_branch_to_projects_is_preserved_without_following(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            data = base / "data"
            projects = base / "projects"
            data.mkdir()
            projects.mkdir()
            (projects / "repo").write_text("keep\n", encoding="utf-8")
            (data / "sandbox").symlink_to(projects, target_is_directory=True)
            (data / "cache").write_text("drop\n", encoding="utf-8")

            uninstall_data.purge_targets([data], [data / "sandbox"])

            self.assertTrue((data / "sandbox").is_symlink())
            self.assertTrue((projects / "repo").is_file())
            self.assertFalse((data / "cache").exists())

    def test_refuses_home_and_symlink_targets(self) -> None:
        with self.assertRaises(ValueError):
            uninstall_data.purge_targets([Path.home()], [])
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            real = base / "real"
            link = base / "link"
            real.mkdir()
            link.symlink_to(real, target_is_directory=True)
            with self.assertRaises(ValueError):
                uninstall_data.purge_targets([link], [])


if __name__ == "__main__":
    unittest.main()
