#!/usr/bin/env python3
"""Unit tests for orcan-context-reflect (loaded as a module despite no .py
extension). Never invokes a real model — subprocess.run is monkeypatched.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "docker" / "rootfs" / "usr" / "local" / "bin" / "orcan-context-reflect"

# Container-only import ("/usr/local/lib") isn't available on the host test
# runner; point it at the repo's copy of the same module instead.
sys.path.insert(0, str(ROOT / "docker" / "rootfs" / "usr" / "local" / "lib"))

_loader = importlib.machinery.SourceFileLoader("orcan_context_reflect", str(SCRIPT_PATH))
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
reflect = importlib.util.module_from_spec(_spec)
_loader.exec_module(reflect)


class ExtractJsonArrayTests(unittest.TestCase):
    def test_plain_array(self) -> None:
        self.assertEqual(reflect.extract_json_array('[{"action": "propose"}]'), [{"action": "propose"}])

    def test_fenced_array(self) -> None:
        raw = '```json\n[{"action": "propose"}]\n```'
        self.assertEqual(reflect.extract_json_array(raw), [{"action": "propose"}])

    def test_empty_array(self) -> None:
        self.assertEqual(reflect.extract_json_array("[]"), [])

    def test_garbage_returns_empty(self) -> None:
        self.assertEqual(reflect.extract_json_array("not json at all"), [])

    def test_non_list_json_returns_empty(self) -> None:
        self.assertEqual(reflect.extract_json_array('{"not": "a list"}'), [])


class InferProjectTests(unittest.TestCase):
    def test_matches_by_workspace_path_prefix(self) -> None:
        ws = {"projects": [
            {"name": "backend", "path": "/repos/backend", "workspace_path": "/ws/backend"},
            {"name": "frontend", "path": "/repos/frontend", "workspace_path": "/ws/frontend"},
        ]}
        self.assertEqual(reflect.infer_project(ws, "/ws/backend/src"), "backend")

    def test_single_project_fallback_when_no_match(self) -> None:
        ws = {"projects": [{"name": "backend", "path": "/repos/backend", "workspace_path": "/ws/backend"}]}
        self.assertEqual(reflect.infer_project(ws, "/somewhere/else"), "backend")

    def test_none_when_multiple_projects_and_no_match(self) -> None:
        ws = {"projects": [
            {"name": "backend", "path": "/repos/backend", "workspace_path": "/ws/backend"},
            {"name": "frontend", "path": "/repos/frontend", "workspace_path": "/ws/frontend"},
        ]}
        self.assertIsNone(reflect.infer_project(ws, "/somewhere/else"))

    def test_empty_cwd_single_project(self) -> None:
        ws = {"projects": [{"name": "backend", "path": "/repos/backend"}]}
        self.assertEqual(reflect.infer_project(ws, ""), "backend")


class ReadNewLinesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "transcript.jsonl"

    def test_missing_file_returns_empty(self) -> None:
        lines, total = reflect.read_new_lines(self.path, 0)
        self.assertEqual(lines, [])
        self.assertEqual(total, 0)

    def test_reads_from_offset(self) -> None:
        self.path.write_text("a\nb\nc\n", encoding="utf-8")
        lines, total = reflect.read_new_lines(self.path, 1)
        self.assertEqual(lines, ["b", "c"])
        self.assertEqual(total, 3)

    def test_offset_beyond_length_restarts(self) -> None:
        self.path.write_text("a\nb\n", encoding="utf-8")
        lines, total = reflect.read_new_lines(self.path, 99)
        self.assertEqual(lines, ["a", "b"])
        self.assertEqual(total, 2)


class StateRoundtripTests(unittest.TestCase):
    def test_missing_state_file_is_empty_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(reflect.load_state(Path(tmp) / "nope.json"), {})

    def test_corrupt_state_file_is_empty_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "state.json"
            p.write_text("{not json", encoding="utf-8")
            self.assertEqual(reflect.load_state(p), {})

    def test_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sub" / "state.json"
            reflect.save_state(p, {"s1": {"turns_since_reflection": 3}})
            self.assertEqual(reflect.load_state(p), {"s1": {"turns_since_reflection": 3}})


class DispatchTests(unittest.TestCase):
    def test_propose_action_builds_expected_args(self) -> None:
        with mock.patch.object(reflect.subprocess, "run") as run:
            reflect.dispatch(
                {"action": "propose", "title": "T", "content": "C", "justification": "J", "kind": "hint"},
                workspace_root=Path("/ws"),
                project="backend",
            )
        run.assert_called_once()
        args = run.call_args.args[0]
        self.assertIn("--project", args)
        self.assertIn("backend", args)
        self.assertIn("--text", args)
        self.assertIn("C", args)
        self.assertIn("--justification", args)
        self.assertIn("J", args)
        self.assertIn("--queue", args)
        self.assertIn("--source", args)
        self.assertIn("reflection", args)

    def test_propose_action_passes_through_epistemic_status_criticality_relations(self) -> None:
        with mock.patch.object(reflect.subprocess, "run") as run:
            reflect.dispatch(
                {
                    "action": "propose",
                    "title": "T",
                    "content": "C",
                    "justification": "J",
                    "epistemic_status": "hypothesis",
                    "criticality": "high",
                    "relations": [{"type": "depends_on", "target_id": "abc123"}],
                },
                workspace_root=Path("/ws"),
                project="backend",
            )
        run.assert_called_once()
        args = run.call_args.args[0]
        self.assertIn("--epistemic-status", args)
        self.assertIn("hypothesis", args)
        self.assertIn("--criticality", args)
        self.assertIn("high", args)
        self.assertIn("--relation", args)
        self.assertIn("depends_on:abc123:backend", args)

    def test_propose_action_omits_optional_fields_when_absent(self) -> None:
        with mock.patch.object(reflect.subprocess, "run") as run:
            reflect.dispatch(
                {"action": "propose", "title": "T", "content": "C", "justification": "J"},
                workspace_root=Path("/ws"),
                project="backend",
            )
        args = run.call_args.args[0]
        self.assertNotIn("--epistemic-status", args)
        self.assertNotIn("--criticality", args)
        self.assertNotIn("--relation", args)

    def test_propose_action_missing_content_is_skipped(self) -> None:
        with mock.patch.object(reflect.subprocess, "run") as run:
            reflect.dispatch(
                {"action": "propose", "justification": "J"},
                workspace_root=Path("/ws"),
                project="backend",
            )
        run.assert_not_called()

    def test_flag_existing_builds_expected_args(self) -> None:
        with mock.patch.object(reflect.subprocess, "run") as run:
            reflect.dispatch(
                {"action": "flag_existing", "id": "abc123", "reason": "stale"},
                workspace_root=Path("/ws"),
                project="backend",
            )
        run.assert_called_once()
        args = run.call_args.args[0]
        self.assertIn("--flag-existing", args)
        self.assertIn("abc123", args)
        self.assertIn("--reason", args)
        self.assertIn("stale", args)

    def test_unknown_action_is_skipped(self) -> None:
        with mock.patch.object(reflect.subprocess, "run") as run:
            reflect.dispatch({"action": "something_else"}, workspace_root=Path("/ws"), project="backend")
        run.assert_not_called()


def _fake_claude_result(actions: list[dict]) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(actions), stderr="")


class MainThresholdTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.workspace_root = Path(self._tmp.name) / "ws"
        self.workspace_root.mkdir()
        self.transcript = Path(self._tmp.name) / "transcript.jsonl"
        self.transcript.write_text("l1\nl2\nl3\n", encoding="utf-8")
        self.config_path = Path(self._tmp.name) / "config.json"
        self.config_path.write_text(
            json.dumps(
                {
                    "workspaces": [
                        {
                            "name": "demo",
                            "root": str(self.workspace_root),
                            "projects": [{"name": "backend", "path": str(self.workspace_root)}],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    def _run_main(self, *, threshold: int, force: bool = False, model_run) -> int:
        argv = [
            "orcan-context-reflect",
            "--session-id", "sess1",
            "--transcript-path", str(self.transcript),
            "--cwd", str(self.workspace_root),
            "--threshold", str(threshold),
        ]
        if force:
            argv.append("--force")
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.dict("os.environ", {"ORCAN_CONFIG": str(self.config_path)}), \
             mock.patch.object(reflect.subprocess, "run", side_effect=model_run):
            return reflect.main()

    def test_below_threshold_never_calls_model(self) -> None:
        model_run = mock.Mock(side_effect=AssertionError("model should not be called below threshold"))
        for _ in range(4):
            self._run_main(threshold=5, model_run=model_run)
        state = reflect.load_state(self.workspace_root / ".orcan" / reflect.STATE_NAME)
        self.assertEqual(state["sess1"]["turns_since_reflection"], 4)
        self.assertEqual(state["sess1"]["last_transcript_line"], 0)

    def test_reaching_threshold_calls_model_and_dispatches(self) -> None:
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)
            if args and args[0] == "claude":
                return _fake_claude_result(
                    [{"action": "propose", "title": "T", "content": "C", "justification": "J", "kind": "fact"}]
                )
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        for _ in range(2):
            self._run_main(threshold=3, model_run=fake_run)
        self._run_main(threshold=3, model_run=fake_run)  # 3rd call hits threshold

        claude_calls = [c for c in calls if c and c[0] == "claude"]
        propose_calls = [c for c in calls if c and str(SCRIPT_PATH.with_name("orcan-context-propose")) in c]
        self.assertEqual(len(claude_calls), 1)
        self.assertEqual(len(propose_calls), 1)

        state = reflect.load_state(self.workspace_root / ".orcan" / reflect.STATE_NAME)
        self.assertEqual(state["sess1"]["turns_since_reflection"], 0)
        self.assertEqual(state["sess1"]["last_transcript_line"], 3)

    def test_force_skips_threshold_on_first_call(self) -> None:
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)
            if args and args[0] == "claude":
                return _fake_claude_result([])
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        self._run_main(threshold=20, force=True, model_run=fake_run)
        claude_calls = [c for c in calls if c and c[0] == "claude"]
        self.assertEqual(len(claude_calls), 1)

    def test_model_call_exception_records_last_error(self) -> None:
        def fake_run(args, **kwargs):
            if args and args[0] == "claude":
                raise subprocess.TimeoutExpired(cmd=args, timeout=120)
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        self._run_main(threshold=20, force=True, model_run=fake_run)
        state = reflect.load_state(self.workspace_root / ".orcan" / reflect.STATE_NAME)
        self.assertIn("model call failed", state["sess1"]["last_error"])
        self.assertIn("last_error_at", state["sess1"])

    def test_model_nonzero_exit_records_last_error(self) -> None:
        def fake_run(args, **kwargs):
            if args and args[0] == "claude":
                return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="boom")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        self._run_main(threshold=20, force=True, model_run=fake_run)
        state = reflect.load_state(self.workspace_root / ".orcan" / reflect.STATE_NAME)
        self.assertIn("model call exited 1", state["sess1"]["last_error"])
        self.assertIn("boom", state["sess1"]["last_error"])

    def test_successful_reflection_clears_previous_error(self) -> None:
        def failing_run(args, **kwargs):
            if args and args[0] == "claude":
                return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="boom")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        self._run_main(threshold=20, force=True, model_run=failing_run)
        state = reflect.load_state(self.workspace_root / ".orcan" / reflect.STATE_NAME)
        self.assertIn("last_error", state["sess1"])

        # New transcript activity so the second call has something to reflect on.
        self.transcript.write_text("l1\nl2\nl3\nl4\nl5\n", encoding="utf-8")

        def ok_run(args, **kwargs):
            if args and args[0] == "claude":
                return _fake_claude_result([])
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        self._run_main(threshold=20, force=True, model_run=ok_run)
        state = reflect.load_state(self.workspace_root / ".orcan" / reflect.STATE_NAME)
        self.assertNotIn("last_error", state["sess1"])
        self.assertNotIn("last_error_at", state["sess1"])


if __name__ == "__main__":
    unittest.main()
