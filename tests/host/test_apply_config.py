#!/usr/bin/env python3
"""Unit tests for apply-config helpers and a tempfile e2e apply."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
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


def _init_repo(path: Path) -> None:
    import subprocess

    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "t"
    env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "t@example.com"
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--quiet", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True, capture_output=True)
    (path / "f").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "f"], cwd=path, check=True, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True, env=env)


def _add_worktree(main_repo: Path, worktree_path: Path, branch: str) -> None:
    import subprocess

    subprocess.run(
        ["git", "worktree", "add", "-b", branch, str(worktree_path)],
        cwd=main_repo, check=True, capture_output=True,
    )


class WorktreeGitDirPathsTests(unittest.TestCase):
    """A git worktree's `.git` is a pointer file into its main checkout's
    git dir — without that shared .git dir also mounted, git commands inside
    the worktree fail with "not a git repository". worktree_git_dir_paths()
    closes that gap by reading the pointer directly, for any worktree
    regardless of how it was created — and mounts *only* `.git`, never the
    main checkout's working-tree files, to keep worktree isolation intact."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_plain_repo_is_ignored(self) -> None:
        repo = self.root / "plain-repo"
        _init_repo(repo)
        result = apply_config.worktree_git_dir_paths({str(repo)})
        self.assertEqual(result, set())

    def test_non_git_directory_is_ignored(self) -> None:
        plain = self.root / "not-a-repo"
        plain.mkdir()
        result = apply_config.worktree_git_dir_paths({str(plain)})
        self.assertEqual(result, set())

    def test_real_worktree_resolves_to_main_repos_git_dir_only(self) -> None:
        main_repo = self.root / "main-checkout"
        _init_repo(main_repo)
        worktree = self.root / "elsewhere" / "linked-worktree"
        worktree.parent.mkdir(parents=True)
        _add_worktree(main_repo, worktree, "feat-x")

        result = apply_config.worktree_git_dir_paths({str(worktree)})
        self.assertEqual(result, {str((main_repo / ".git").resolve())})
        # Isolation: the main checkout root itself must never be the mount target.
        self.assertNotIn(str(main_repo.resolve()), result)

    def test_malformed_git_file_does_not_raise(self) -> None:
        fake = self.root / "fake-worktree"
        fake.mkdir()
        (fake / ".git").write_text("not a real pointer\n", encoding="utf-8")
        result = apply_config.worktree_git_dir_paths({str(fake)})
        self.assertEqual(result, set())


class ManagedRootTests(unittest.TestCase):
    """A project path already under the managed root needs no bind entry of
    its own — it's covered by the one stable base-compose mount — which is
    what lets adding/removing such a project skip a container recreate."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _workspace(self, name: str, project_path: Path) -> dict:
        return {
            "name": name,
            "root": f"/home/developer/workspaces/{name}",
            "meta_path": str(self.root / "workspaces" / name),
            "tmux_session": name,
            "project_count": 1,
            "projects": [
                {
                    "name": project_path.name,
                    "path": str(project_path),
                    "workspace_path": f"/home/developer/workspaces/{name}/{project_path.name}",
                    "container_path": str(project_path),
                }
            ],
        }

    def test_managed_root_env_lookup(self) -> None:
        self.assertIsNone(apply_config.managed_projects_root({}))
        self.assertEqual(
            apply_config.managed_projects_root({"ORCAN_PROJECTS_ROOT": "/x/projects"}),
            Path("/x/projects"),
        )

    def test_project_under_managed_root_gets_no_bind_line(self) -> None:
        managed = self.root / "managed" / "projects"
        proj = managed / "demo"
        proj.mkdir(parents=True)
        ws = self._workspace("demo", proj)

        text = apply_config.write_compose_projects([ws], self.root, managed_root=managed)

        self.assertNotIn(f"{proj}:{proj}", text)

    def test_project_outside_managed_root_still_gets_bind_line(self) -> None:
        managed = self.root / "managed" / "projects"
        external = self.root / "external" / "demo"
        external.mkdir(parents=True)
        ws = self._workspace("demo", external)

        text = apply_config.write_compose_projects([ws], self.root, managed_root=managed)

        self.assertIn(f"{external}:{external}", text)

    def test_no_managed_root_keeps_legacy_per_project_binds(self) -> None:
        proj = self.root / "anywhere" / "demo"
        proj.mkdir(parents=True)
        ws = self._workspace("demo", proj)

        text = apply_config.write_compose_projects([ws], self.root, managed_root=None)

        self.assertIn(f"{proj}:{proj}", text)


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
                    "font_size": 19,
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

            runtime = root / "mounts" / "runtime-config.json"
            compose = root / "mounts" / "compose-projects.generated.yml"
            manifest = root / "workspaces" / "index.json"
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

    def test_stop_hook_seeded_on_first_sync_and_disable_sticks(self) -> None:
        import claude_hook as ch

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
                        "projects": [{"name": "app", "path": str(proj.resolve())}],
                    }
                ]
            }
            (root / "orcan.config.json").write_text(
                json.dumps(cfg, indent=2) + "\n", encoding="utf-8"
            )

            def sync() -> None:
                old_argv = sys.argv
                try:
                    sys.argv = [
                        "apply-config.py",
                        "--root", str(root),
                        "--config", str(root / "orcan.config.json"),
                    ]
                    apply_config.main()
                finally:
                    sys.argv = old_argv

            meta_path = root / "workspaces" / "demo"

            sync()
            self.assertTrue(ch.has_hook(ch.load_settings(ch.settings_path(meta_path))))

            ch.disable(meta_path, dry_run=False)
            self.assertFalse(ch.has_hook(ch.load_settings(ch.settings_path(meta_path))))

            sync()
            self.assertFalse(
                ch.has_hook(ch.load_settings(ch.settings_path(meta_path))),
                "a second sync must not re-enable a hook the user explicitly disabled",
            )

    def test_stop_hook_missing_gets_reported_not_silently_ignored(self) -> None:
        import claude_hook as ch

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
                        "projects": [{"name": "app", "path": str(proj.resolve())}],
                    }
                ]
            }
            (root / "orcan.config.json").write_text(
                json.dumps(cfg, indent=2) + "\n", encoding="utf-8"
            )

            def sync() -> str:
                old_argv = sys.argv
                buf = io.StringIO()
                try:
                    sys.argv = [
                        "apply-config.py",
                        "--root", str(root),
                        "--config", str(root / "orcan.config.json"),
                    ]
                    with contextlib.redirect_stdout(buf):
                        apply_config.main()
                finally:
                    sys.argv = old_argv
                return buf.getvalue()

            meta_path = root / "workspaces" / "demo"

            # Simulate a settings.json that existed before the seed step ever
            # ran for this workspace (e.g. copied by init-workspace's
            # missing-only template before the first `orcan sync`).
            (meta_path / ".claude").mkdir(parents=True)
            (meta_path / ".claude" / "settings.json").write_text(
                json.dumps({"permissions": {"deny": []}}, indent=2) + "\n", encoding="utf-8"
            )

            out = sync()
            self.assertFalse(ch.has_hook(ch.load_settings(ch.settings_path(meta_path))))
            self.assertIn("Stop hook not active for workspace 'demo'", out)
            self.assertIn("orcan context hook enable demo", out)

    def test_worktree_project_also_mounts_main_repos_git_dir_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main_repo = root / "main-checkout"
            _init_repo(main_repo)
            worktree_path = root / "elsewhere" / "linked-worktree"
            worktree_path.parent.mkdir(parents=True)
            _add_worktree(main_repo, worktree_path, "feat-x")

            (root / ".env.example").write_text(
                "USER_UID=1000\nUSER_GID=1000\n", encoding="utf-8"
            )
            cfg = {
                "workspaces": [
                    {
                        "name": "demo",
                        "projects": [{"name": "app", "path": str(worktree_path)}],
                    }
                ]
            }
            (root / "orcan.config.json").write_text(
                json.dumps(cfg, indent=2) + "\n", encoding="utf-8"
            )

            old_argv = sys.argv
            try:
                sys.argv = [
                    "apply-config.py",
                    "--root", str(root),
                    "--config", str(root / "orcan.config.json"),
                ]
                apply_config.main()
            finally:
                sys.argv = old_argv

            compose_text = (root / "mounts" / "compose-projects.generated.yml").read_text(encoding="utf-8")
            self.assertIn(str(worktree_path.resolve()), compose_text)
            self.assertIn(str((main_repo / ".git").resolve()), compose_text)
            # Isolation: never a bare mount of the main checkout's own root
            # (only its .git dir — a substring check on the root alone would
            # false-positive against the .git line above, so check the exact
            # "path:path" mapping line the main checkout root would produce).
            self.assertNotIn(f"{main_repo.resolve()}:{main_repo.resolve()}", compose_text)


if __name__ == "__main__":
    unittest.main()
