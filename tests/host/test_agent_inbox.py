#!/usr/bin/env python3
"""Unit tests for the agent task handoff/inbox lifecycle (orcan.agent_inbox)."""

from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _orcan_lib_loader import load_orcan_module  # noqa: E402

agent_inbox = load_orcan_module("agent_inbox")


class ProposeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_default_policy_is_approve_and_lands_in_proposals(self) -> None:
        path = agent_inbox.propose(self.root, {"title": "do X"})
        self.assertTrue(path.is_file())
        self.assertIn("proposals", path.parts)
        self.assertEqual(agent_inbox.list_tasks(self.root, "inbox"), [])
        proposed = agent_inbox.list_tasks(self.root, "proposals")
        self.assertEqual(len(proposed), 1)
        self.assertEqual(proposed[0]["execution"]["policy"], "approve")
        self.assertEqual(proposed[0]["status"], "proposed")

    def test_draft_policy_lands_in_proposals_too(self) -> None:
        agent_inbox.propose(self.root, {"title": "sketch", "execution": {"policy": "draft"}})
        self.assertEqual(len(agent_inbox.list_tasks(self.root, "proposals")), 1)
        self.assertEqual(agent_inbox.list_tasks(self.root, "inbox"), [])

    def test_auto_policy_goes_straight_to_inbox(self) -> None:
        agent_inbox.propose(self.root, {"title": "auto task", "execution": {"policy": "auto"}})
        self.assertEqual(agent_inbox.list_tasks(self.root, "proposals"), [])
        inbox = agent_inbox.list_tasks(self.root, "inbox")
        self.assertEqual(len(inbox), 1)
        self.assertEqual(inbox[0]["status"], "approved")

    def test_unknown_policy_rejected(self) -> None:
        with self.assertRaises(ValueError):
            agent_inbox.propose(self.root, {"execution": {"policy": "yolo"}})


class ApproveTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_approve_moves_proposal_to_inbox(self) -> None:
        path = agent_inbox.propose(self.root, {"title": "do X"})
        task_id = path.stem

        agent_inbox.approve(self.root, task_id)

        self.assertEqual(agent_inbox.list_tasks(self.root, "proposals"), [])
        inbox = agent_inbox.list_tasks(self.root, "inbox")
        self.assertEqual(len(inbox), 1)
        self.assertEqual(inbox[0]["status"], "approved")

    def test_approve_refuses_draft_policy(self) -> None:
        path = agent_inbox.propose(self.root, {"execution": {"policy": "draft"}})
        with self.assertRaises(ValueError):
            agent_inbox.approve(self.root, path.stem)
        # Untouched — still sitting in proposals/.
        self.assertEqual(len(agent_inbox.list_tasks(self.root, "proposals")), 1)

    def test_approve_missing_task_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            agent_inbox.approve(self.root, "task-doesnotexist")


class ClaimTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_claim_moves_to_processing_and_stamps_claimant(self) -> None:
        path = agent_inbox.propose(self.root, {"execution": {"policy": "auto"}})
        task_id = path.stem

        claimed = agent_inbox.claim(self.root, task_id, "worker-1")

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["status"], "processing")
        self.assertEqual(claimed["claimed_by"], "worker-1")
        self.assertEqual(agent_inbox.list_tasks(self.root, "inbox"), [])
        self.assertEqual(len(agent_inbox.list_tasks(self.root, "processing")), 1)

    def test_second_claim_of_same_task_returns_none(self) -> None:
        path = agent_inbox.propose(self.root, {"execution": {"policy": "auto"}})
        task_id = path.stem

        first = agent_inbox.claim(self.root, task_id, "worker-1")
        second = agent_inbox.claim(self.root, task_id, "worker-2")

        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_concurrent_claim_only_one_worker_wins(self) -> None:
        """The core "no double-claim" guarantee from AGENTS.md §16 — many
        threads racing claim_next() against one task must yield exactly one
        winner, proven under real concurrency, not just sequential calls."""
        agent_inbox.propose(self.root, {"execution": {"policy": "auto"}})

        winners: list[dict] = []
        lock = threading.Lock()

        def worker(name: str) -> None:
            claimed = agent_inbox.claim_next(self.root, name)
            if claimed is not None:
                with lock:
                    winners.append(claimed)

        threads = [threading.Thread(target=worker, args=(f"worker-{i}",)) for i in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(winners), 1)
        self.assertEqual(len(agent_inbox.list_tasks(self.root, "processing")), 1)

    def test_claim_next_returns_none_when_inbox_empty(self) -> None:
        self.assertIsNone(agent_inbox.claim_next(self.root, "worker-1"))


class CompleteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_complete_done_moves_out_of_processing(self) -> None:
        path = agent_inbox.propose(self.root, {"execution": {"policy": "auto"}})
        agent_inbox.claim(self.root, path.stem, "worker-1")

        agent_inbox.complete(self.root, path.stem, outcome="done", result={"ok": True})

        self.assertEqual(agent_inbox.list_tasks(self.root, "processing"), [])
        done = agent_inbox.list_tasks(self.root, "done")
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0]["result"], {"ok": True})

    def test_complete_failed_goes_to_failed_state(self) -> None:
        path = agent_inbox.propose(self.root, {"execution": {"policy": "auto"}})
        agent_inbox.claim(self.root, path.stem, "worker-1")

        agent_inbox.complete(self.root, path.stem, outcome="failed")

        self.assertEqual(len(agent_inbox.list_tasks(self.root, "failed")), 1)

    def test_complete_unknown_outcome_rejected(self) -> None:
        path = agent_inbox.propose(self.root, {"execution": {"policy": "auto"}})
        agent_inbox.claim(self.root, path.stem, "worker-1")
        with self.assertRaises(ValueError):
            agent_inbox.complete(self.root, path.stem, outcome="whatever")


if __name__ == "__main__":
    unittest.main()
