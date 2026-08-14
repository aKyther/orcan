#!/usr/bin/env python3
"""Unit tests for config-wizard's cwd-based defaulting (suggest_cwd_project)."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "repository"
sys.path.insert(0, str(SCRIPTS))

# Module file is "config-wizard.py" (hyphen) — not importable by name directly.
_spec = importlib.util.spec_from_file_location("config_wizard", SCRIPTS / "config-wizard.py")
cw = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(cw)


class SuggestCwdProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.cwd = Path(self._tmp.name).resolve()

    def test_suggests_name_and_path_for_plain_directory(self) -> None:
        with patch.object(cw.Path, "cwd", return_value=self.cwd):
            result = cw.suggest_cwd_project(None)
        self.assertEqual(result, (self.cwd.name, str(self.cwd)))

    def test_none_when_already_mounted_in_cfg(self) -> None:
        cfg = {
            "workspaces": [
                {"name": "ws", "projects": [{"name": "p", "path": str(self.cwd)}]}
            ]
        }
        with patch.object(cw.Path, "cwd", return_value=self.cwd):
            result = cw.suggest_cwd_project(cfg)
        self.assertIsNone(result)

    def test_none_for_sensitive_path(self) -> None:
        with patch.object(cw.Path, "cwd", return_value=Path("/etc")):
            result = cw.suggest_cwd_project(None)
        self.assertIsNone(result)

    def test_none_cfg_behaves_like_empty_cfg(self) -> None:
        with patch.object(cw.Path, "cwd", return_value=self.cwd):
            self.assertEqual(cw.suggest_cwd_project(None), cw.suggest_cwd_project({}))


class AskNewWorkspaceCwdDefaultTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.cwd = Path(self._tmp.name).resolve()

    def test_enter_enter_accepts_cwd_as_workspace_and_project(self) -> None:
        """The whole point: pressing Enter through every prompt should mount
        cwd as both the workspace name and the sole project's path — no
        typing required, like `uv init` / `poetry init`."""
        with patch.object(cw.Path, "cwd", return_value=self.cwd), patch(
            "builtins.input", side_effect=["", "", "", ""]
        ):
            ws = cw.ask_new_workspace(another=False, cfg=None)
        self.assertEqual(ws["name"], self.cwd.name)
        self.assertEqual(len(ws["projects"]), 1)
        self.assertEqual(ws["projects"][0]["path"], str(self.cwd))
        self.assertEqual(ws["projects"][0]["name"], self.cwd.name)

    def test_no_suggestion_when_cwd_already_in_cfg(self) -> None:
        cfg = {
            "workspaces": [
                {"name": "ws", "projects": [{"name": "p", "path": str(self.cwd)}]}
            ]
        }
        typed_name = "my-typed-workspace"
        with patch.object(cw.Path, "cwd", return_value=self.cwd), patch(
            "builtins.input",
            side_effect=[typed_name, str(self.cwd), "proj", ""],
        ):
            ws = cw.ask_new_workspace(another=True, cfg=cfg)
        self.assertEqual(ws["name"], typed_name)


class FindCwdMatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.cwd = Path(self._tmp.name).resolve()

    def test_none_when_not_registered(self) -> None:
        with patch.object(cw.Path, "cwd", return_value=self.cwd):
            self.assertIsNone(cw.find_cwd_match({"workspaces": []}))

    def test_finds_workspace_and_project_name(self) -> None:
        cfg = {
            "workspaces": [
                {"name": "myws", "projects": [{"name": "proj", "path": str(self.cwd)}]}
            ]
        }
        with patch.object(cw.Path, "cwd", return_value=self.cwd):
            result = cw.find_cwd_match(cfg)
        self.assertEqual(result, ("myws", "proj", str(self.cwd)))


class MainAlreadyConfiguredTests(unittest.TestCase):
    """`orcan init` run from a directory already mounted somewhere in the
    config: default is a one-line confirmation + early exit (sync still runs
    afterward, in the bash wrapper), not a forced reconfigure flow."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.project = self.root / "proj"
        self.project.mkdir()
        self.config_path = self.root / "orcan.config.json"
        self.config_path.write_text(
            json.dumps(
                {
                    "workspaces": [
                        {
                            "name": "myws",
                            "projects": [
                                {"name": "proj", "path": str(self.project.resolve())}
                            ],
                        }
                    ]
                }
            )
        )
        self.argv = [
            "config-wizard.py",
            "--root",
            str(self.root),
            "--config",
            str(self.config_path),
        ]

    def test_declining_change_exits_without_touching_config(self) -> None:
        before = self.config_path.read_text()
        with patch.object(cw.Path, "cwd", return_value=self.project), patch(
            "sys.argv", self.argv
        ), patch("sys.stdin.isatty", return_value=True), patch(
            "builtins.input", side_effect=["n"]
        ):
            cw.main()
        self.assertEqual(self.config_path.read_text(), before)

    def test_accepting_change_falls_through_to_the_normal_edit_flow(self) -> None:
        # y=change anything, edit=top_menu action, ""=keep this workspace,
        # ""=no more projects, ""=no more workspaces, n=decline final save.
        answers = ["y", "edit", "", "", "", "n"]
        before = self.config_path.read_text()
        with patch.object(cw.Path, "cwd", return_value=self.project), patch(
            "sys.argv", self.argv
        ), patch("sys.stdin.isatty", return_value=True), patch(
            "builtins.input", side_effect=answers
        ):
            cw.main()
        # declined the final save too, so config is still untouched
        self.assertEqual(self.config_path.read_text(), before)


class PathCompleterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "workspaces").mkdir()
        (self.root / "worktrees").mkdir()
        (self.root / "afile.txt").write_text("x")

    def _matches(self, text: str) -> list[str]:
        out = []
        state = 0
        while True:
            m = cw._path_completer(text, state)
            if m is None:
                break
            out.append(m)
            state += 1
        return out

    def test_completes_matching_subdirectories_with_trailing_slash(self) -> None:
        matches = self._matches(f"{self.root}/wo")
        self.assertEqual(
            sorted(matches),
            sorted([f"{self.root}/workspaces/", f"{self.root}/worktrees/"]),
        )

    def test_excludes_plain_files(self) -> None:
        matches = self._matches(f"{self.root}/af")
        self.assertEqual(matches, [])

    def test_no_matches_returns_none_at_end(self) -> None:
        self.assertIsNone(cw._path_completer(f"{self.root}/nope", 0))

    def test_expands_tilde_for_listing_but_preserves_typed_prefix(self) -> None:
        with patch.object(cw.os.path, "expanduser", return_value=str(self.root) + "/wo"):
            matches = self._matches("~/wo")
        # the returned completion keeps the "~" the user typed, not the
        # expanded /home/... form
        self.assertTrue(all(m.startswith("~/") for m in matches))


class OfferPullBeforeWorktreeTests(unittest.TestCase):
    """cw._offer_pull_before_worktree — the wizard-side wiring; git_worktrees'
    own pull_current_branch() has its own real-git integration tests in
    test_git_worktrees.py."""

    def test_detached_head_skips_question_entirely(self) -> None:
        import git_worktrees as gw

        with patch.object(gw, "current_branch", return_value=""), patch(
            "builtins.input"
        ) as mock_input:
            cw._offer_pull_before_worktree(Path("/tmp/whatever"), prefix="  ")
        mock_input.assert_not_called()

    def test_declining_skips_pull(self) -> None:
        import git_worktrees as gw

        with patch.object(gw, "current_branch", return_value="main"), patch.object(
            gw, "pull_current_branch"
        ) as pull, patch("builtins.input", side_effect=["n"]):
            cw._offer_pull_before_worktree(Path("/tmp/whatever"), prefix="  ")
        pull.assert_not_called()

    def test_accepting_calls_pull_current_branch(self) -> None:
        import git_worktrees as gw

        with patch.object(gw, "current_branch", return_value="main"), patch.object(
            gw, "pull_current_branch", return_value=(True, "Already up to date.")
        ) as pull, patch("builtins.input", side_effect=["y"]):
            cw._offer_pull_before_worktree(Path("/tmp/whatever"), prefix="  ")
        pull.assert_called_once_with(Path("/tmp/whatever"))

    def test_default_enter_accepts_the_pull(self) -> None:
        """ask_yes_no's default is True ("Y/n") — bare Enter should pull."""
        import git_worktrees as gw

        with patch.object(gw, "current_branch", return_value="main"), patch.object(
            gw, "pull_current_branch", return_value=(True, "Already up to date.")
        ) as pull, patch("builtins.input", side_effect=[""]):
            cw._offer_pull_before_worktree(Path("/tmp/whatever"), prefix="  ")
        pull.assert_called_once()


if __name__ == "__main__":
    unittest.main()
