#!/usr/bin/env python3
"""Unit tests for the AgentExecutor abstraction (orcan.agent_executor)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _orcan_lib_loader import load_orcan_module  # noqa: E402

agent_inbox = load_orcan_module("agent_inbox")
agent_executor = load_orcan_module("agent_executor")


class BuildPromptTests(unittest.TestCase):
    def test_includes_only_present_sections(self) -> None:
        prompt = agent_executor.build_prompt({"title": "T", "goal": "G"})
        self.assertIn("# T", prompt)
        self.assertIn("## Goal", prompt)
        self.assertIn("G", prompt)
        self.assertNotIn("## Constraints", prompt)

    def test_never_includes_a_full_transcript_field(self) -> None:
        # The whole point of the manifest is that it's NOT the discussion
        # transcript — build_prompt only ever renders the known structured
        # fields, so an arbitrary "transcript" key on the task is silently
        # dropped, not leaked into the executor's prompt.
        prompt = agent_executor.build_prompt(
            {"title": "T", "goal": "G", "transcript": "the entire chat log..."}
        )
        self.assertNotIn("entire chat log", prompt)


class ShellExecutorTests(unittest.TestCase):
    def test_runs_command_in_given_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = agent_executor.ShellExecutor()
            result = executor.execute(
                {"execution": {"command": "pwd"}}, {"cwd": tmp}
            )
            self.assertTrue(result.ok)
            self.assertIn(str(Path(tmp).resolve()), result.output)

    def test_failing_command_is_not_ok(self) -> None:
        executor = agent_executor.ShellExecutor()
        result = executor.execute({"execution": {"command": "exit 3"}}, {"cwd": "."})
        self.assertFalse(result.ok)
        self.assertEqual(result.returncode, 3)

    def test_missing_command_is_not_ok(self) -> None:
        executor = agent_executor.ShellExecutor()
        result = executor.execute({"execution": {}}, {"cwd": "."})
        self.assertFalse(result.ok)


class DispatchOnceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_claims_executes_and_marks_done_on_success(self) -> None:
        agent_inbox.propose(
            self.root,
            {"title": "echo", "execution": {"policy": "auto", "command": "echo hi"}},
        )

        completed = agent_executor.dispatch_once(
            self.root, agent_executor.ShellExecutor(), "worker-1"
        )

        self.assertIsNotNone(completed)
        self.assertEqual(completed["status"], "done")
        self.assertEqual(agent_inbox.list_tasks(self.root, "inbox"), [])
        self.assertEqual(agent_inbox.list_tasks(self.root, "processing"), [])
        done = agent_inbox.list_tasks(self.root, "done")
        self.assertEqual(len(done), 1)
        self.assertIn("hi", done[0]["result"]["output"])

    def test_failure_lands_in_failed_not_done(self) -> None:
        agent_inbox.propose(
            self.root,
            {"title": "boom", "execution": {"policy": "auto", "command": "exit 1"}},
        )

        completed = agent_executor.dispatch_once(
            self.root, agent_executor.ShellExecutor(), "worker-1"
        )

        self.assertEqual(completed["status"], "failed")
        self.assertEqual(len(agent_inbox.list_tasks(self.root, "failed")), 1)
        self.assertEqual(agent_inbox.list_tasks(self.root, "done"), [])

    def test_empty_inbox_returns_none(self) -> None:
        self.assertIsNone(
            agent_executor.dispatch_once(self.root, agent_executor.ShellExecutor(), "worker-1")
        )


if __name__ == "__main__":
    unittest.main()
