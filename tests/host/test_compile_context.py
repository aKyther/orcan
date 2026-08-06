#!/usr/bin/env python3
"""Unit tests for compile_context: inbox/decisions import + review queue."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "repository"))

import compile_context as cc  # noqa: E402
import context_assertions as ca  # noqa: E402


def init_repo(path: Path) -> None:
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


def drop_json(directory: Path, payload: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid.uuid4().hex[:12]}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class CompileContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.data = root / "orcan-data"
        os.environ["ORCAN_DATA"] = str(self.data)
        self.addCleanup(os.environ.pop, "ORCAN_DATA", None)

        self.backend = root / "projects" / "backend"
        init_repo(self.backend)

        self.meta_path = root / "meta" / "demo"
        self.meta_path.mkdir(parents=True)
        self.orcan_dir = self.meta_path / ".orcan"

        self.ws = {
            "name": "demo",
            "meta_path": str(self.meta_path),
            "projects": [{"name": "backend", "path": str(self.backend)}],
        }

    def test_inbox_item_becomes_proposed(self) -> None:
        drop_json(
            self.orcan_dir / cc.INBOX_DIRNAME,
            {
                "project_name": "backend",
                "title": "Deps",
                "content": "Use uv, not pip.",
                "kind": "fact",
                "justification": "Avoid mixed envs",
                "applicability": {},
                "decision": None,
            },
        )
        cc.compile_workspace(self.ws)

        items = ca.list_objects(self.backend, status="proposed")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Deps")
        # inbox drop consumed
        self.assertEqual(list((self.orcan_dir / cc.INBOX_DIRNAME).glob("*.json")), [])

    def test_inbox_item_with_accept_decision_ends_accepted_and_compiles(self) -> None:
        drop_json(
            self.orcan_dir / cc.INBOX_DIRNAME,
            {
                "project_name": "backend",
                "title": "Deps",
                "content": "Use uv, not pip.",
                "justification": "Avoid mixed envs",
                "decision": "accept",
            },
        )
        cc.compile_workspace(self.ws)

        accepted = ca.list_objects(self.backend, status="accepted")
        self.assertEqual(len(accepted), 1)
        pack = (self.meta_path / cc.OUTPUT_NAME).read_text(encoding="utf-8")
        self.assertIn("Deps", pack)
        self.assertIn("Avoid mixed envs", pack)

    def test_invalid_json_is_quarantined_not_fatal(self) -> None:
        bad = self.orcan_dir / cc.INBOX_DIRNAME / "bad.json"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text("{not json", encoding="utf-8")

        cc.compile_workspace(self.ws)  # must not raise

        self.assertFalse(bad.exists())
        self.assertTrue(bad.with_name("bad.json.invalid").exists())

    def test_unknown_project_is_quarantined(self) -> None:
        drop = drop_json(
            self.orcan_dir / cc.INBOX_DIRNAME,
            {"project_name": "does-not-exist", "content": "x", "justification": "y"},
        )
        cc.compile_workspace(self.ws)
        self.assertFalse(drop.exists())
        self.assertTrue(drop.with_name(drop.name + ".invalid").exists())
        self.assertEqual(ca.list_objects(self.backend), [])

    def test_missing_justification_is_quarantined(self) -> None:
        drop = drop_json(
            self.orcan_dir / cc.INBOX_DIRNAME,
            {"project_name": "backend", "content": "x", "justification": ""},
        )
        cc.compile_workspace(self.ws)
        self.assertTrue(drop.with_name(drop.name + ".invalid").exists())

    def test_decision_file_transitions_existing_proposed_item(self) -> None:
        obj = ca.propose(self.backend, content="c", justification="j")
        drop_json(
            self.orcan_dir / cc.DECISIONS_DIRNAME,
            {"id": obj["id"], "project_name": "backend", "decision": "accept"},
        )
        cc.compile_workspace(self.ws)
        self.assertEqual(ca.get_object(self.backend, obj["id"])["status"], "accepted")
        self.assertEqual(list((self.orcan_dir / cc.DECISIONS_DIRNAME).glob("*.json")), [])

    def test_decision_for_already_resolved_id_is_idempotent(self) -> None:
        obj = ca.propose(self.backend, content="c", justification="j")
        ca.accept(self.backend, obj["id"])
        drop_json(
            self.orcan_dir / cc.DECISIONS_DIRNAME,
            {"id": obj["id"], "project_name": "backend", "decision": "reject"},
        )
        cc.compile_workspace(self.ws)  # must not raise despite already-accepted status
        self.assertEqual(ca.get_object(self.backend, obj["id"])["status"], "accepted")

    def test_review_queue_lists_only_proposed_items_for_this_workspace(self) -> None:
        proposed = ca.propose(self.backend, content="still pending", justification="j")
        accepted = ca.propose(self.backend, content="already decided", justification="j")
        ca.accept(self.backend, accepted["id"])

        cc.compile_workspace(self.ws)

        queue = json.loads((self.orcan_dir / cc.REVIEW_QUEUE_NAME).read_text(encoding="utf-8"))
        ids = [i["id"] for i in queue["candidates"]]
        self.assertIn(proposed["id"], ids)
        self.assertNotIn(accepted["id"], ids)
        self.assertEqual(queue["candidates"][0]["project_name"], "backend")
        self.assertEqual(queue["reconsider"], [])

    def test_review_queue_regenerates_to_empty_when_nothing_pending(self) -> None:
        cc.compile_workspace(self.ws)
        queue = json.loads((self.orcan_dir / cc.REVIEW_QUEUE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(queue, {"candidates": [], "reconsider": []})

    # -- flag-existing / reconsider / retire / keep -----------------------------

    def test_flag_existing_creates_reconsider_entry(self) -> None:
        obj = ca.propose(self.backend, content="stale?", justification="j")
        ca.accept(self.backend, obj["id"])
        drop_json(
            self.orcan_dir / cc.INBOX_DIRNAME,
            {"project_name": "backend", "flag_existing_id": obj["id"], "reason": "seems outdated"},
        )
        cc.compile_workspace(self.ws)

        self.assertTrue((self.orcan_dir / cc.FLAGS_DIRNAME / f"{obj['id']}.json").is_file())
        queue = json.loads((self.orcan_dir / cc.REVIEW_QUEUE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(queue["candidates"], [])
        self.assertEqual(len(queue["reconsider"]), 1)
        self.assertEqual(queue["reconsider"][0]["id"], obj["id"])
        self.assertEqual(queue["reconsider"][0]["reason"], "seems outdated")

    def test_flag_existing_rejects_non_accepted_id(self) -> None:
        obj = ca.propose(self.backend, content="still pending", justification="j")  # not accepted
        drop = drop_json(
            self.orcan_dir / cc.INBOX_DIRNAME,
            {"project_name": "backend", "flag_existing_id": obj["id"], "reason": "why not"},
        )
        cc.compile_workspace(self.ws)
        self.assertTrue(drop.with_name(drop.name + ".invalid").exists())

    def test_flag_existing_unknown_id_quarantined(self) -> None:
        drop = drop_json(
            self.orcan_dir / cc.INBOX_DIRNAME,
            {"project_name": "backend", "flag_existing_id": "doesnotexist", "reason": "why not"},
        )
        cc.compile_workspace(self.ws)
        self.assertTrue(drop.with_name(drop.name + ".invalid").exists())

    def test_decision_retire_resolves_flag_and_retires(self) -> None:
        obj = ca.propose(self.backend, content="stale?", justification="j")
        ca.accept(self.backend, obj["id"])
        drop_json(
            self.orcan_dir / cc.INBOX_DIRNAME,
            {"project_name": "backend", "flag_existing_id": obj["id"], "reason": "seems outdated"},
        )
        cc.compile_workspace(self.ws)  # turns the flag into context-flags/<id>.json

        drop_json(
            self.orcan_dir / cc.DECISIONS_DIRNAME,
            {"id": obj["id"], "project_name": "backend", "decision": "retire"},
        )
        cc.compile_workspace(self.ws)

        self.assertEqual(ca.get_object(self.backend, obj["id"])["status"], "retired")
        self.assertFalse((self.orcan_dir / cc.FLAGS_DIRNAME / f"{obj['id']}.json").exists())
        queue = json.loads((self.orcan_dir / cc.REVIEW_QUEUE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(queue["reconsider"], [])

    def test_decision_keep_clears_flag_without_mutating_store(self) -> None:
        obj = ca.propose(self.backend, content="fine actually", justification="j")
        ca.accept(self.backend, obj["id"])
        drop_json(
            self.orcan_dir / cc.INBOX_DIRNAME,
            {"project_name": "backend", "flag_existing_id": obj["id"], "reason": "double-check this"},
        )
        cc.compile_workspace(self.ws)

        drop_json(
            self.orcan_dir / cc.DECISIONS_DIRNAME,
            {"id": obj["id"], "project_name": "backend", "decision": "keep"},
        )
        cc.compile_workspace(self.ws)

        self.assertEqual(ca.get_object(self.backend, obj["id"])["status"], "accepted")
        self.assertFalse((self.orcan_dir / cc.FLAGS_DIRNAME / f"{obj['id']}.json").exists())
        queue = json.loads((self.orcan_dir / cc.REVIEW_QUEUE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(queue["reconsider"], [])
        # still selectable / compiled since it's still accepted
        pack = (self.meta_path / cc.OUTPUT_NAME).read_text(encoding="utf-8")
        self.assertIn("fine actually", pack)

    def test_rendered_pack_includes_assertion_id(self) -> None:
        obj = ca.propose(self.backend, content="x", justification="j")
        ca.accept(self.backend, obj["id"])
        cc.compile_workspace(self.ws)
        pack = (self.meta_path / cc.OUTPUT_NAME).read_text(encoding="utf-8")
        self.assertIn(obj["id"], pack)

    # -- RFC-0002: epistemic_status / criticality / relations pass through ---

    def test_inbox_passes_through_epistemic_status_criticality(self) -> None:
        drop_json(
            self.orcan_dir / cc.INBOX_DIRNAME,
            {
                "project_name": "backend",
                "content": "maybe true",
                "justification": "j",
                "epistemic_status": "hypothesis",
                "criticality": "high",
                "decision": "accept",
            },
        )
        cc.compile_workspace(self.ws)
        accepted = ca.list_objects(self.backend, status="accepted")
        self.assertEqual(len(accepted), 1)
        full = ca.get_object(self.backend, accepted[0]["id"])
        self.assertEqual(full["epistemic_status"], "hypothesis")
        self.assertEqual(full["criticality"], "high")

    def test_rendered_pack_shows_epistemic_status_and_relations(self) -> None:
        target = ca.propose(self.backend, content="target fact", justification="j")
        ca.accept(self.backend, target["id"])
        source = ca.propose(
            self.backend, content="source fact", justification="j",
            epistemic_status="interpretation", criticality="high",
            relations=[{"type": "depends_on", "target_id": target["id"], "target_project": str(self.backend)}],
        )
        ca.accept(self.backend, source["id"])

        cc.compile_workspace(self.ws)
        pack = (self.meta_path / cc.OUTPUT_NAME).read_text(encoding="utf-8")
        self.assertIn("epistemic status: interpretation", pack)
        self.assertIn("criticality: high", pack)
        self.assertIn("depends_on", pack)
        self.assertIn("target fact", pack)  # resolved title, not just the raw id

    def test_review_queue_candidates_include_epistemic_status_and_relations(self) -> None:
        target = ca.propose(self.backend, content="target", justification="j")
        ca.accept(self.backend, target["id"])
        ca.propose(
            self.backend, content="source", justification="j",
            epistemic_status="hypothesis",
            relations=[{"type": "risk_of", "target_id": target["id"], "target_project": str(self.backend)}],
        )
        cc.compile_workspace(self.ws)
        queue = json.loads((self.orcan_dir / cc.REVIEW_QUEUE_NAME).read_text(encoding="utf-8"))
        candidate = queue["candidates"][0]
        self.assertEqual(candidate["epistemic_status"], "hypothesis")
        self.assertEqual(candidate["relations"][0]["type"], "risk_of")

    def test_prints_zero_compiled_when_nothing_accepted(self) -> None:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cc.compile_workspace(self.ws)
        self.assertIn("0 assertions compiled for workspace 'demo'", buf.getvalue())

    def test_prints_count_compiled_when_something_accepted(self) -> None:
        obj = ca.propose(self.backend, content="fact", justification="j")
        ca.accept(self.backend, obj["id"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cc.compile_workspace(self.ws)
        self.assertIn("1 assertion(s) compiled into CONTEXT-ASSERTIONS.md for workspace 'demo'", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
