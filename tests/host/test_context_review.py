#!/usr/bin/env python3
"""Unit tests for orcan-context-review (loaded as a module despite no .py
extension). Never invokes a real model — subprocess.run is monkeypatched.
"""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "docker" / "rootfs" / "usr" / "local" / "bin" / "orcan-context-review"

# The script does `sys.path.insert(0, "/usr/local/lib")` itself before
# importing orcan.context_inbox — harmless on a bare host, but wrong if this
# happens to run *inside* an orcan container (as this session does), where
# that path is a real, possibly-stale directory that would otherwise shadow
# the repo's copy. Pre-register the repo's orcan.context_inbox in
# sys.modules first so the script's later `from orcan.context_inbox import
# ...` finds it there regardless of what sys.path resolves to.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _orcan_lib_loader import load_orcan_module  # noqa: E402

load_orcan_module("context_inbox")

_loader = importlib.machinery.SourceFileLoader("orcan_context_review", str(SCRIPT_PATH))
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
review = importlib.util.module_from_spec(_spec)
_loader.exec_module(review)


def _fake_claude_result(payload: list[dict], *, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=json.dumps(payload), stderr="")


class ExtractJsonArrayTests(unittest.TestCase):
    def test_plain_array(self) -> None:
        self.assertEqual(review.extract_json_array('[{"verdict": "novel"}]'), [{"verdict": "novel"}])

    def test_fenced_array(self) -> None:
        raw = '```json\n[{"verdict": "novel"}]\n```'
        self.assertEqual(review.extract_json_array(raw), [{"verdict": "novel"}])

    def test_empty_array(self) -> None:
        self.assertEqual(review.extract_json_array("[]"), [])

    def test_garbage_returns_empty(self) -> None:
        self.assertEqual(review.extract_json_array("not json at all"), [])

    def test_non_list_json_returns_empty(self) -> None:
        self.assertEqual(review.extract_json_array('{"not": "a list"}'), [])


class BuildCheckPromptTests(unittest.TestCase):
    def test_includes_candidate_fields_and_existing_context(self) -> None:
        candidates = [{"id": "cand1", "title": "T1", "content": "C1"}]
        prompt = review.build_check_prompt(candidates, "EXISTING CONTEXT HERE")
        self.assertIn("cand1", prompt)
        self.assertIn("T1", prompt)
        self.assertIn("C1", prompt)
        self.assertIn("EXISTING CONTEXT HERE", prompt)


class RunDuplicateCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.workspace_root = Path(self._tmp.name)
        self._which = mock.patch.object(review.shutil, "which", return_value="/usr/bin/claude")
        self._which.start()
        self.addCleanup(self._which.stop)

    def test_no_candidates_skips_model_call(self) -> None:
        with mock.patch.object(review.subprocess, "run") as run:
            result = review.run_duplicate_check([], self.workspace_root, "haiku")
        run.assert_not_called()
        self.assertEqual(result, {})

    def test_missing_context_assertions_md_skips_model_call(self) -> None:
        with mock.patch.object(review.subprocess, "run") as run:
            result = review.run_duplicate_check(
                [{"id": "cand1", "title": "T", "content": "C"}], self.workspace_root, "haiku"
            )
        run.assert_not_called()
        self.assertEqual(result, {})

    def test_missing_claude_skips_without_subprocess(self) -> None:
        (self.workspace_root / "CONTEXT-ASSERTIONS.md").write_text("existing", encoding="utf-8")
        with mock.patch.object(review.shutil, "which", return_value=None), mock.patch.object(
            review.subprocess, "run"
        ) as run, mock.patch.object(review, "warn") as warn:
            result = review.run_duplicate_check(
                [{"id": "cand1", "title": "T", "content": "C"}], self.workspace_root, "haiku"
            )
        run.assert_not_called()
        self.assertEqual(result, {})
        warn.assert_called_once()
        self.assertIn("claude not on PATH", warn.call_args.args[0])

    def test_model_call_never_touches_stdin(self) -> None:
        (self.workspace_root / "CONTEXT-ASSERTIONS.md").write_text("existing", encoding="utf-8")
        with mock.patch.object(review.subprocess, "run", return_value=_fake_claude_result([])) as run:
            review.run_duplicate_check(
                [{"id": "cand1", "title": "T", "content": "C"}], self.workspace_root, "haiku"
            )
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0][0], "/usr/bin/claude")
        self.assertEqual(run.call_args.kwargs.get("stdin"), subprocess.DEVNULL)

    def test_keeps_only_duplicate_and_conflict_verdicts(self) -> None:
        (self.workspace_root / "CONTEXT-ASSERTIONS.md").write_text("existing", encoding="utf-8")
        payload = [
            {"candidate_id": "cand1", "verdict": "novel"},
            {"candidate_id": "cand2", "verdict": "duplicate", "related_title": "X"},
            {"candidate_id": "cand3", "verdict": "conflict", "related_title": "Y"},
        ]
        with mock.patch.object(review.subprocess, "run", return_value=_fake_claude_result(payload)):
            result = review.run_duplicate_check(
                [
                    {"id": "cand1", "title": "T1", "content": "C1"},
                    {"id": "cand2", "title": "T2", "content": "C2"},
                    {"id": "cand3", "title": "T3", "content": "C3"},
                ],
                self.workspace_root,
                "haiku",
            )
        self.assertEqual(set(result), {"cand2", "cand3"})
        self.assertEqual(result["cand2"]["related_title"], "X")

    def test_nonzero_returncode_is_best_effort_empty(self) -> None:
        (self.workspace_root / "CONTEXT-ASSERTIONS.md").write_text("existing", encoding="utf-8")
        with mock.patch.object(
            review.subprocess, "run", return_value=_fake_claude_result([], returncode=1)
        ):
            result = review.run_duplicate_check(
                [{"id": "cand1", "title": "T", "content": "C"}], self.workspace_root, "haiku"
            )
        self.assertEqual(result, {})

    def test_subprocess_error_is_best_effort_empty(self) -> None:
        (self.workspace_root / "CONTEXT-ASSERTIONS.md").write_text("existing", encoding="utf-8")
        with mock.patch.object(review.subprocess, "run", side_effect=OSError("no such binary")):
            result = review.run_duplicate_check(
                [{"id": "cand1", "title": "T", "content": "C"}], self.workspace_root, "haiku"
            )
        self.assertEqual(result, {})

    def test_timeout_is_best_effort_empty(self) -> None:
        (self.workspace_root / "CONTEXT-ASSERTIONS.md").write_text("existing", encoding="utf-8")
        with mock.patch.object(
            review.subprocess, "run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=120)
        ):
            result = review.run_duplicate_check(
                [{"id": "cand1", "title": "T", "content": "C"}], self.workspace_root, "haiku"
            )
        self.assertEqual(result, {})


class ReviewCandidatesAnnotationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.decisions_dir = Path(self._tmp.name) / "decisions"
        self.workspace_root = Path(self._tmp.name)

    def _run(self, items: list[dict], annotations: dict[str, dict], answers: list[str]) -> str:
        buf = io.StringIO()
        with mock.patch("builtins.input", side_effect=answers), contextlib.redirect_stdout(buf):
            review.review_candidates(items, self.decisions_dir, annotations, self.workspace_root)
        return buf.getvalue()

    def test_prints_note_title_and_body_clearly(self) -> None:
        items = [
            {
                "id": "cand1",
                "project_name": "orcan",
                "title": "Preview item 7",
                "content": "Dense fixture row 7 for scrolling and review.",
                "justification": "Developer UX busy-state fixture.",
            }
        ]
        buf = io.StringIO()
        with mock.patch("builtins.input", side_effect=["s"]) as inp, contextlib.redirect_stdout(buf):
            review.review_candidates(items, self.decisions_dir, {}, self.workspace_root)
        out = buf.getvalue()
        self.assertIn("NOTE (this text becomes lasting project context if you accept)", out)
        self.assertIn("Title: Preview item 7", out)
        self.assertIn("Body:  Dense fixture row 7 for scrolling and review.", out)
        self.assertIn("Why proposed: Developer UX busy-state fixture.", out)
        inp.assert_called_with(
            f"  {review.BOLD}{review.CYAN}Accept this note into project context? "
            f"[y]es / [n]o / [s]kip:{review.RESET} "
        )

    def test_prints_conflict_warning_line(self) -> None:
        items = [{"id": "cand1", "project_name": "orcan", "title": "T", "content": "C", "justification": "J"}]
        annotations = {"cand1": {"verdict": "conflict", "related_title": "Existing thing"}}
        out = self._run(items, annotations, ["s"])
        self.assertIn("may conflict with existing", out)

    def test_no_annotation_no_warning_line(self) -> None:
        items = [{"id": "cand1", "project_name": "orcan", "title": "T", "content": "C", "justification": "J"}]
        out = self._run(items, {}, ["s"])
        self.assertNotIn("⚠", out)

    def test_skip_records_no_decision(self) -> None:
        items = [{"id": "cand1", "project_name": "orcan", "title": "T", "content": "C", "justification": "J"}]
        self._run(items, {}, ["s"])
        self.assertFalse(self.decisions_dir.exists())

    def test_yes_records_accept_decision(self) -> None:
        items = [{"id": "cand1", "project_name": "orcan", "title": "T", "content": "C", "justification": "J"}]
        self._run(items, {}, ["y"])
        drops = list(self.decisions_dir.glob("*.json"))
        self.assertEqual(len(drops), 1)
        decision = json.loads(drops[0].read_text())
        self.assertEqual(decision["decision"], "accept")
        self.assertEqual(decision["id"], "cand1")

    def test_no_consolidation_offer_without_drafted_content(self) -> None:
        items = [{"id": "cand1", "project_name": "orcan", "title": "T", "content": "C", "justification": "J"}]
        annotations = {"cand1": {"verdict": "duplicate", "related_title": "X"}}  # no consolidated_content
        out = self._run(items, annotations, ["y"])  # single answer — no follow-up should be asked
        self.assertNotIn("consolidated version", out)

    def test_accepting_consolidation_offer_queues_it(self) -> None:
        items = [{"id": "cand1", "project_name": "orcan", "title": "T", "content": "C", "justification": "J"}]
        annotations = {
            "cand1": {
                "verdict": "duplicate",
                "related_id": "abc123",
                "related_title": "Existing thing",
                "consolidated_title": "Merged",
                "consolidated_content": "Merged content",
            }
        }
        with mock.patch.object(review, "queue_consolidation", return_value=True) as queue:
            out = self._run(items, annotations, ["y", "y"])
        queue.assert_called_once()
        called_item, called_note, called_root = queue.call_args.args
        self.assertEqual(called_item["id"], "cand1")
        self.assertEqual(called_note["related_id"], "abc123")
        self.assertEqual(called_root, self.workspace_root)
        self.assertIn("Queued", out)

    def test_declining_consolidation_offer_does_not_queue(self) -> None:
        items = [{"id": "cand1", "project_name": "orcan", "title": "T", "content": "C", "justification": "J"}]
        annotations = {
            "cand1": {
                "verdict": "duplicate",
                "related_id": "abc123",
                "related_title": "Existing thing",
                "consolidated_title": "Merged",
                "consolidated_content": "Merged content",
            }
        }
        with mock.patch.object(review, "queue_consolidation") as queue:
            self._run(items, annotations, ["y", "n"])
        queue.assert_not_called()

    def test_rejecting_candidate_skips_consolidation_offer(self) -> None:
        items = [{"id": "cand1", "project_name": "orcan", "title": "T", "content": "C", "justification": "J"}]
        annotations = {
            "cand1": {
                "verdict": "duplicate",
                "related_id": "abc123",
                "consolidated_title": "Merged",
                "consolidated_content": "Merged content",
            }
        }
        with mock.patch.object(review, "queue_consolidation") as queue:
            self._run(items, annotations, ["n"])  # reject, not accept — no offer at all
        queue.assert_not_called()


class ReviewReconsiderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.decisions_dir = Path(self._tmp.name) / "decisions"

    def test_retire_records_decision_and_renders_reason(self) -> None:
        item = {
            "id": "old1",
            "project_name": "orcan",
            "title": "Old note",
            "content": "No longer true",
            "reason": "superseded",
        }
        buf = io.StringIO()
        with mock.patch("builtins.input", side_effect=["r"]), contextlib.redirect_stdout(buf):
            decided = review.review_reconsider([item], self.decisions_dir)
        self.assertEqual(decided, 1)
        self.assertIn("already accepted, flagged", buf.getvalue())
        self.assertIn("Why flagged now: superseded", buf.getvalue())
        drops = list(self.decisions_dir.glob("*.json"))
        self.assertEqual(len(drops), 1)
        self.assertEqual(json.loads(drops[0].read_text())["decision"], "retire")

    def test_skip_does_not_write_decision(self) -> None:
        item = {"id": "old1", "project_name": "orcan", "title": "Old note"}
        with mock.patch("builtins.input", side_effect=["s"]):
            self.assertEqual(review.review_reconsider([item], self.decisions_dir), 0)
        self.assertFalse(self.decisions_dir.exists())


class QueueConsolidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.workspace_root = Path(self._tmp.name)
        self.item = {"id": "cand1", "project_name": "orcan"}
        self.note = {
            "related_id": "abc123",
            "consolidated_title": "Merged",
            "consolidated_content": "Merged content",
        }

    def test_missing_required_fields_skips_without_subprocess(self) -> None:
        with mock.patch.object(review.subprocess, "run") as run:
            result = review.queue_consolidation(self.item, {}, self.workspace_root)
        run.assert_not_called()
        self.assertFalse(result)

    def test_makes_two_calls_with_devnull_stdin(self) -> None:
        with mock.patch.object(
            review.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")
        ) as run:
            result = review.queue_consolidation(self.item, self.note, self.workspace_root)
        self.assertTrue(result)
        self.assertEqual(run.call_count, 2)
        for call in run.call_args_list:
            self.assertEqual(call.kwargs.get("stdin"), subprocess.DEVNULL)

    def test_first_call_proposes_consolidated_content(self) -> None:
        with mock.patch.object(
            review.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")
        ) as run:
            review.queue_consolidation(self.item, self.note, self.workspace_root)
        propose_args = run.call_args_list[0].args[0]
        self.assertIn("--text", propose_args)
        self.assertIn("Merged content", propose_args)
        self.assertIn("--source", propose_args)
        self.assertIn("consolidation", propose_args)
        self.assertIn("--queue", propose_args)

    def test_second_call_flags_related_id_for_retirement(self) -> None:
        with mock.patch.object(
            review.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")
        ) as run:
            review.queue_consolidation(self.item, self.note, self.workspace_root)
        flag_args = run.call_args_list[1].args[0]
        self.assertIn("--flag-existing", flag_args)
        self.assertIn("abc123", flag_args)

    def test_returns_false_on_nonzero_exit(self) -> None:
        with mock.patch.object(
            review.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "boom")
        ):
            result = review.queue_consolidation(self.item, self.note, self.workspace_root)
        self.assertFalse(result)

    def test_returns_false_on_subprocess_error(self) -> None:
        with mock.patch.object(review.subprocess, "run", side_effect=OSError("no binary")):
            result = review.queue_consolidation(self.item, self.note, self.workspace_root)
        self.assertFalse(result)


class MainNoCheckFlagTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.workspace_root = Path(self._tmp.name) / "ws"
        (self.workspace_root / ".orcan").mkdir(parents=True)
        (self.workspace_root / "CONTEXT-ASSERTIONS.md").write_text("existing", encoding="utf-8")
        queue = {
            "candidates": [
                {"id": "cand1", "project_name": "orcan", "title": "T", "content": "C", "justification": "J"}
            ],
            "reconsider": [],
        }
        (self.workspace_root / ".orcan" / "context-review-queue.json").write_text(
            json.dumps(queue), encoding="utf-8"
        )

    def _run_main(self, extra_argv: list[str]) -> None:
        argv = ["orcan-context-review", str(self.workspace_root), *extra_argv]
        with mock.patch.object(sys, "argv", argv), mock.patch("builtins.input", side_effect=["s"]):
            review.main()

    def test_no_check_flag_skips_duplicate_check(self) -> None:
        with mock.patch.object(review, "run_duplicate_check") as check:
            self._run_main(["--no-check"])
        check.assert_not_called()

    def test_default_runs_duplicate_check(self) -> None:
        with mock.patch.object(review, "run_duplicate_check", return_value={}) as check:
            self._run_main([])
        check.assert_called_once()


class LoadInboxCandidatesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.workspace_root = Path(self._tmp.name)
        self.inbox = self.workspace_root / ".orcan" / "context-inbox"
        self.inbox.mkdir(parents=True)

    def drop(self, name: str, payload: dict) -> Path:
        path = self.inbox / f"{name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_missing_inbox_dir_returns_empty(self) -> None:
        empty_root = Path(self._tmp.name) / "no-inbox-here"
        empty_root.mkdir()
        self.assertEqual(review.load_inbox_candidates(empty_root), [])

    def test_includes_undecided_candidate_with_id_from_filename(self) -> None:
        self.drop("a1b2c3", {"project_name": "orcan", "title": "T", "content": "C", "justification": "J"})
        items = review.load_inbox_candidates(self.workspace_root)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "a1b2c3")
        self.assertEqual(items[0]["project_name"], "orcan")
        self.assertEqual(items[0]["_source"], "inbox")
        self.assertEqual(items[0]["_drop_path"], self.inbox / "a1b2c3.json")

    def test_skips_flag_existing_drops(self) -> None:
        self.drop("flag1", {"project_name": "orcan", "flag_existing_id": "abc123", "reason": "stale"})
        self.assertEqual(review.load_inbox_candidates(self.workspace_root), [])

    def test_skips_already_decided_drops(self) -> None:
        self.drop(
            "decided1",
            {"project_name": "orcan", "title": "T", "content": "C", "justification": "J", "decision": "accept"},
        )
        self.assertEqual(review.load_inbox_candidates(self.workspace_root), [])

    def test_skips_malformed_json(self) -> None:
        (self.inbox / "bad.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(review.load_inbox_candidates(self.workspace_root), [])

    def test_sorted_oldest_to_newest_by_mtime(self) -> None:
        import os
        import time

        p1 = self.drop("first", {"project_name": "orcan", "title": "T1", "content": "C1", "justification": "J"})
        time.sleep(0.01)
        p2 = self.drop("second", {"project_name": "orcan", "title": "T2", "content": "C2", "justification": "J"})
        now = time.time()
        os.utime(p1, (now - 100, now - 100))
        os.utime(p2, (now - 1, now - 1))
        items = review.load_inbox_candidates(self.workspace_root)
        self.assertEqual([it["id"] for it in items], ["first", "second"])


class WriteInboxDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.drop_path = Path(self._tmp.name) / "drop.json"

    def test_sets_decision_and_preserves_other_fields(self) -> None:
        self.drop_path.write_text(
            json.dumps({"project_name": "orcan", "title": "T", "content": "C", "decision": None}),
            encoding="utf-8",
        )
        review.write_inbox_decision(self.drop_path, "accept")
        payload = json.loads(self.drop_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["decision"], "accept")
        self.assertEqual(payload["title"], "T")
        self.assertEqual(payload["content"], "C")

    def test_missing_file_warns_without_raising(self) -> None:
        missing = Path(self._tmp.name) / "nope.json"
        review.write_inbox_decision(missing, "accept")  # must not raise


class ReviewCandidatesInboxWriteBackTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.decisions_dir = Path(self._tmp.name) / "decisions"
        self.workspace_root = Path(self._tmp.name)
        self.drop_path = Path(self._tmp.name) / "drop.json"
        self.drop_path.write_text(
            json.dumps({"project_name": "orcan", "title": "T", "content": "C", "justification": "J"}),
            encoding="utf-8",
        )

    def test_accepting_inbox_item_rewrites_drop_not_decisions_dir(self) -> None:
        item = {
            "id": "drop",
            "_source": "inbox",
            "_drop_path": self.drop_path,
            "project_name": "orcan",
            "title": "T",
            "content": "C",
            "justification": "J",
        }
        with mock.patch("builtins.input", side_effect=["y"]):
            review.review_candidates([item], self.decisions_dir, {}, self.workspace_root)
        self.assertFalse(self.decisions_dir.exists())
        payload = json.loads(self.drop_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["decision"], "accept")

    def test_accepting_queue_item_still_uses_decisions_dir(self) -> None:
        item = {
            "id": "cand1",
            "_source": "queue",
            "project_name": "orcan",
            "title": "T",
            "content": "C",
            "justification": "J",
        }
        with mock.patch("builtins.input", side_effect=["y"]):
            review.review_candidates([item], self.decisions_dir, {}, self.workspace_root)
        drops = list(self.decisions_dir.glob("*.json"))
        self.assertEqual(len(drops), 1)
        decision = json.loads(drops[0].read_text())
        self.assertEqual(decision["decision"], "accept")
        self.assertEqual(decision["id"], "cand1")
        # the unrelated inbox-style fixture file must be untouched by this path
        self.assertNotIn("decision", json.loads(self.drop_path.read_text(encoding="utf-8")))


class MainMergesInboxAndQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.workspace_root = Path(self._tmp.name) / "ws"
        self.inbox = self.workspace_root / ".orcan" / "context-inbox"
        self.inbox.mkdir(parents=True)

    def _run_main(self, argv_extra: list[str], answers: list[str]) -> str:
        buf = io.StringIO()
        argv = ["orcan-context-review", str(self.workspace_root), "--no-check", *argv_extra]
        with mock.patch.object(sys, "argv", argv), mock.patch(
            "builtins.input", side_effect=answers
        ), contextlib.redirect_stdout(buf):
            review.main()
        return buf.getvalue()

    def test_inbox_only_works_without_review_queue_file(self) -> None:
        (self.inbox / "a1.json").write_text(
            json.dumps({"project_name": "orcan", "title": "T", "content": "C", "justification": "J"}),
            encoding="utf-8",
        )
        out = self._run_main([], ["s"])
        self.assertIn("1 new candidate(s)", out)
        self.assertNotIn("run `orcan sync`", out)

    def test_merges_inbox_and_queue_candidates_with_labeled_counts(self) -> None:
        (self.inbox / "a1.json").write_text(
            json.dumps({"project_name": "orcan", "title": "T1", "content": "C1", "justification": "J"}),
            encoding="utf-8",
        )
        queue = {
            "candidates": [
                {"id": "cand1", "project_name": "orcan", "title": "T2", "content": "C2", "justification": "J"}
            ],
            "reconsider": [],
        }
        (self.workspace_root / ".orcan" / "context-review-queue.json").write_text(
            json.dumps(queue), encoding="utf-8"
        )
        out = self._run_main([], ["s", "s"])
        self.assertIn("2 new candidate(s)", out)
        self.assertIn("1 fresh from inbox, 1 already queued", out)

    def test_no_pending_when_both_sources_empty(self) -> None:
        out = self._run_main([], [])
        self.assertIn("No pending context assertions.", out)


if __name__ == "__main__":
    unittest.main()
