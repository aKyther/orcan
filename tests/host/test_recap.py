#!/usr/bin/env python3
"""Unit tests for orcan.recap cascading compact."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "docker" / "rootfs" / "usr" / "local" / "lib"))

from orcan.recap import (  # noqa: E402
    MergeResult,
    flush_rolling_to_inbox,
    get_last_transcript_line,
    merge_rolling,
    new_cascade_state,
    process_one_batch,
    recap_state_path,
    set_last_transcript_line,
)
from orcan.session_scan import SessionRef, lines_for_turn_batch  # noqa: E402


def _user_line(agent: str, text: str = "hi") -> str:
    if agent == "claude":
        return json.dumps({"type": "user", "message": {"content": text}})
    return json.dumps({"role": "user", "message": {"content": [{"type": "text", "text": text}]}})


class LinesForTurnBatchTests(unittest.TestCase):
    def test_stops_after_n_user_turns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            lines = [_user_line("claude", str(i)) for i in range(25)]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            session = SessionRef("claude", "s", path, "/ws")
            batch, end, turns = lines_for_turn_batch(session, 0, 20)
            self.assertEqual(turns, 20)
            self.assertEqual(end, 20)
            self.assertEqual(len(batch), 20)


class MergeRollingTests(unittest.TestCase):
    def test_no_previous_returns_batch(self) -> None:
        result = merge_rolling("", "batch facts", "(none)", model="haiku", runner=lambda _p: "{}")
        self.assertEqual(result.rolling_compact, "batch facts")
        self.assertFalse(result.drift)

    def test_parses_drift_response(self) -> None:
        def runner(_prompt: str) -> str:
            return json.dumps(
                {"drift": True, "drift_reason": "new topic", "rolling_compact": "fresh start"}
            )

        result = merge_rolling("old", "new batch", "(none)", model="haiku", runner=runner)
        self.assertTrue(result.drift)
        self.assertEqual(result.rolling_compact, "fresh start")


class ProcessOneBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ws = Path(self._tmp.name) / "demo"
        self.orcan = self.ws / ".orcan"
        self.orcan.mkdir(parents=True)
        (self.ws / "CONTEXT-ASSERTIONS.md").write_text("# none\n", encoding="utf-8")
        self.transcript = self.orcan / "sess.jsonl"
        self.transcript.write_text("\n".join(_user_line("claude", str(i)) for i in range(22)) + "\n")
        self.session = SessionRef("claude", "sess", self.transcript, str(self.ws))
        self.propose = Path(self._tmp.name) / "propose.py"
        self.propose.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n", encoding="utf-8")
        self.propose.chmod(0o755)

    def test_first_batch_creates_recap_state(self) -> None:
        calls: list[str] = []

        def runner(prompt: str) -> str:
            calls.append(prompt[:40])
            if "merge" in prompt.lower() or "Previous rolling" in prompt:
                return json.dumps({"drift": False, "rolling_compact": "merged"})
            return "- fact one"

        queued, worked = process_one_batch(
            self.session,
            self.ws,
            project="orcan",
            branch="main",
            threshold=20,
            model="haiku",
            dry_run=False,
            flush_remaining=False,
            propose_bin=self.propose,
            runner=runner,
        )
        self.assertTrue(worked)
        self.assertEqual(queued, 0)
        state = json.loads(recap_state_path(self.ws, "sess").read_text(encoding="utf-8"))
        self.assertIn("rolling_compact", state)
        self.assertEqual(get_last_transcript_line(self.ws, "sess"), 20)

    def test_drift_flushes_previous_rolling(self) -> None:
        (self.orcan / "recap").mkdir(parents=True, exist_ok=True)
        recap_state_path(self.ws, "sess").write_text(
            json.dumps(new_cascade_state(rolling_compact="old durable fact")) + "\n",
            encoding="utf-8",
        )
        set_last_transcript_line(self.ws, "sess", 0)
        self.transcript.write_text("\n".join(_user_line("claude", str(i)) for i in range(20)) + "\n")

        def runner(prompt: str) -> str:
            if "Rolling recap to promote" in prompt:
                return json.dumps(
                    [
                        {
                            "action": "propose",
                            "title": "Old",
                            "content": "old durable fact",
                            "justification": "learned earlier",
                        }
                    ]
                )
            if "Previous rolling" in prompt:
                return json.dumps(
                    {"drift": True, "drift_reason": "different task", "rolling_compact": "new topic seed"}
                )
            return "- new batch fact"

        with mock.patch("orcan.recap.subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            queued, worked = process_one_batch(
                self.session,
                self.ws,
                project="orcan",
                branch="main",
                threshold=20,
                model="haiku",
                dry_run=False,
                flush_remaining=False,
                propose_bin=self.propose,
                runner=runner,
            )
        self.assertTrue(worked)
        self.assertEqual(queued, 1)
        state = json.loads(recap_state_path(self.ws, "sess").read_text(encoding="utf-8"))
        self.assertEqual(state["rolling_compact"], "new topic seed")
        self.assertEqual(state["generation"], 2)


if __name__ == "__main__":
    unittest.main()
