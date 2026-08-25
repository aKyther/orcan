#!/usr/bin/env python3
"""Unit tests for orcan.session_scan (Claude + Cursor transcript discovery)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "docker" / "rootfs" / "usr" / "local" / "lib"))

from orcan.session_scan import (  # noqa: E402
    SessionRef,
    count_turns,
    discover_sessions,
    encode_claude_project_dir,
    encode_cursor_project_dir,
    is_turn_line,
    lines_for_turn_batch,
    state_key,
    unread_turn_count,
)


class EncodeTests(unittest.TestCase):
    def test_claude_encoding_matches_observed_layout(self) -> None:
        # Observed: ~/.claude/projects/-home-developer-workspaces-orcan-dev/
        cwd = Path("/home/developer/workspaces/orcan-dev")
        self.assertEqual(
            encode_claude_project_dir(cwd),
            "-home-developer-workspaces-orcan-dev",
        )

    def test_cursor_encoding_matches_observed_layout(self) -> None:
        cwd = Path("/home/developer/workspaces/orcan-dev")
        self.assertEqual(
            encode_cursor_project_dir(cwd),
            "home-developer-workspaces-orcan-dev",
        )


class TurnCountTests(unittest.TestCase):
    def test_claude_counts_real_user_not_tool_result(self) -> None:
        real = json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}})
        tool = json.dumps(
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "tool_result", "content": "ok"}],
                },
            }
        )
        asst = json.dumps({"type": "assistant", "message": {"role": "assistant"}})
        self.assertTrue(is_turn_line("claude", real))
        self.assertFalse(is_turn_line("claude", tool))
        self.assertFalse(is_turn_line("claude", asst))
        self.assertEqual(count_turns("claude", [real, tool, asst, real]), 2)

    def test_cursor_counts_user_role(self) -> None:
        user = json.dumps({"role": "user", "message": {"content": [{"type": "text", "text": "x"}]}})
        asst = json.dumps({"role": "assistant", "message": {"content": []}})
        self.assertTrue(is_turn_line("cursor", user))
        self.assertFalse(is_turn_line("cursor", asst))
        self.assertEqual(count_turns("cursor", [user, asst, user]), 2)

    def test_garbage_line_is_not_a_turn(self) -> None:
        self.assertFalse(is_turn_line("claude", "not-json"))
        self.assertFalse(is_turn_line("cursor", "{"))


class DiscoverTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.ws = self.root / "workspaces" / "demo"
        self.ws.mkdir(parents=True)
        self.claude = self.root / "claude"
        self.cursor = self.root / "cursor"
        (self.claude / "projects").mkdir(parents=True)
        (self.cursor / "projects").mkdir(parents=True)

    def _write_claude(self, cwd: Path, session_id: str, lines: list[str]) -> Path:
        proj = self.claude / "projects" / encode_claude_project_dir(cwd)
        proj.mkdir(parents=True, exist_ok=True)
        path = proj / f"{session_id}.jsonl"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        # nested subagent must be ignored
        sub = proj / session_id / "subagents"
        sub.mkdir(parents=True, exist_ok=True)
        (sub / "agent-nested.jsonl").write_text("{}\n", encoding="utf-8")
        return path

    def _write_cursor(self, cwd: Path, session_id: str, lines: list[str]) -> Path:
        base = self.cursor / "projects" / encode_cursor_project_dir(cwd) / "agent-transcripts" / session_id
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"{session_id}.jsonl"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_discovers_claude_and_cursor_for_workspace(self) -> None:
        claude_lines = [json.dumps({"type": "user", "message": {"content": "a"}})]
        cursor_lines = [json.dumps({"role": "user", "message": {"content": []}})]
        self._write_claude(self.ws, "sess-claude", claude_lines)
        self._write_cursor(self.ws, "sess-cursor", cursor_lines)

        found = discover_sessions(
            self.ws,
            claude_root=self.claude,
            cursor_root=self.cursor,
        )
        self.assertEqual({(s.agent, s.session_id) for s in found}, {("claude", "sess-claude"), ("cursor", "sess-cursor")})

    def test_discovers_project_checkout_cwd(self) -> None:
        project = self.ws / "backend"
        project.mkdir()
        self._write_claude(project, "in-project", [json.dumps({"type": "user", "message": {"content": "x"}})])
        found = discover_sessions(
            self.ws,
            project_paths=[project],
            claude_root=self.claude,
            cursor_root=self.cursor,
            agents=["claude"],
        )
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].cwd, str(project.resolve()))

    def test_agents_filter(self) -> None:
        self._write_claude(self.ws, "c1", ["{}"])
        self._write_cursor(self.ws, "u1", ["{}"])
        found = discover_sessions(
            self.ws,
            agents=["cursor"],
            claude_root=self.claude,
            cursor_root=self.cursor,
        )
        self.assertEqual([s.agent for s in found], ["cursor"])


class StateKeyAndUnreadTests(unittest.TestCase):
    def test_claude_state_key_is_bare_for_hook_sharing(self) -> None:
        s = SessionRef("claude", "abc", Path("/t.jsonl"), "/ws")
        self.assertEqual(state_key(s), "abc")

    def test_cursor_state_key_is_namespaced(self) -> None:
        s = SessionRef("cursor", "abc", Path("/t.jsonl"), "/ws")
        self.assertEqual(state_key(s), "cursor:abc")

    def test_unread_turn_count_from_offset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            lines = [
                json.dumps({"type": "user", "message": {"content": "1"}}),
                json.dumps({"type": "assistant", "message": {}}),
                json.dumps({"type": "user", "message": {"content": "2"}}),
            ]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            session = SessionRef("claude", "s", path, "/ws")
            turns, total, new = unread_turn_count(session, 1)
            self.assertEqual(total, 3)
            self.assertEqual(turns, 1)
            self.assertEqual(len(new), 2)

    def test_lines_for_turn_batch_caps_at_max_turns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            lines = [
                json.dumps({"type": "user", "message": {"content": "1"}}),
                json.dumps({"type": "assistant", "message": {}}),
                json.dumps({"type": "user", "message": {"content": "2"}}),
                json.dumps({"type": "user", "message": {"content": "3"}}),
            ]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            session = SessionRef("claude", "s", path, "/ws")
            batch, end, turns = lines_for_turn_batch(session, 0, 2)
            self.assertEqual(turns, 2)
            self.assertEqual(end, 3)
            self.assertEqual(len(batch), 3)


if __name__ == "__main__":
    unittest.main()
