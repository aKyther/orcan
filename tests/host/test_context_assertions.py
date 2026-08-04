#!/usr/bin/env python3
"""Unit tests for context_assertions: lifecycle, applicability, selection."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "repository"))

import context_assertions as ca  # noqa: E402


def init_repo(path: Path, *, branch: str = "main") -> None:
    # Some hosts export empty GIT_AUTHOR_*/GIT_COMMITTER_* (e.g. after `orcan
    # sync` with no host git identity — see update-env.sh's own warning about
    # this). Those env vars outrank local `git config`, so pin them here too.
    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "t"
    env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "t@example.com"
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--quiet", "-b", branch], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True, capture_output=True)
    (path / "f").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "f"], cwd=path, check=True, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True, env=env)


class ContextAssertionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.data = root / "orcan-data"
        os.environ["ORCAN_DATA"] = str(self.data)
        self.addCleanup(os.environ.pop, "ORCAN_DATA", None)

        self.backend = root / "projects" / "backend"
        self.contracts = root / "projects" / "contracts"
        self.mobile = root / "projects" / "mobile"
        init_repo(self.backend)
        init_repo(self.contracts)
        init_repo(self.mobile)

    # -- identity ---------------------------------------------------------

    def test_project_id_stable_and_distinguishes_same_basename(self) -> None:
        other = Path(self._tmp.name) / "elsewhere" / "backend"
        other.mkdir(parents=True)
        self.assertEqual(ca.project_id(self.backend), ca.project_id(self.backend))
        self.assertNotEqual(ca.project_id(self.backend), ca.project_id(other))

    def test_worktree_of_same_repo_shares_project_id_with_main_checkout(self) -> None:
        """A branch worktree lives at its own path but shares the repo's
        common git dir — it must resolve to the same anchor as the main
        checkout, not start from an empty store."""
        worktree_path = Path(self._tmp.name) / "worktrees" / "backend-feature-x"
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "worktree", "add", "-b", "feature-x", str(worktree_path)],
            cwd=self.backend,
            check=True,
            capture_output=True,
        )
        self.assertEqual(ca.project_id(self.backend), ca.project_id(worktree_path))

    def test_unrelated_repo_with_same_basename_as_a_worktree_stays_distinct(self) -> None:
        unrelated = Path(self._tmp.name) / "other-org" / "backend"
        init_repo(unrelated)
        self.assertNotEqual(ca.project_id(self.backend), ca.project_id(unrelated))

    def test_worktree_shares_store_so_assertions_carry_over_gated_by_branch(self) -> None:
        worktree_path = Path(self._tmp.name) / "worktrees" / "backend-release"
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "worktree", "add", "-b", "release/1.0", str(worktree_path)],
            cwd=self.backend,
            check=True,
            capture_output=True,
        )
        obj = ca.propose(
            self.backend,
            content="release freeze rules",
            justification="j",
            applicability={"branch": ["release/*"]},
        )
        ca.accept(self.backend, obj["id"])

        # authored against the main checkout path, but selection through the
        # worktree path must see it too — same anchor, gated by branch.
        via_worktree = ca.select_for_workspace(
            "ws", [{"name": "backend", "path": str(worktree_path)}]
        )
        via_main_on_main_branch = ca.select_for_workspace(
            "ws", [{"name": "backend", "path": str(self.backend)}]
        )
        self.assertEqual(len(via_worktree), 1)
        self.assertEqual(via_main_on_main_branch, [])

    # -- lifecycle ----------------------------------------------------------

    def test_propose_requires_content_and_justification(self) -> None:
        with self.assertRaises(SystemExit):
            ca.propose(self.backend, content="", justification="why")
        with self.assertRaises(SystemExit):
            ca.propose(self.backend, content="text", justification="")

    def test_proposed_is_not_selected_until_accepted(self) -> None:
        ca.propose(self.backend, content="Use uv, not pip.", justification="Avoid mixed envs")
        selected = ca.select_for_workspace(
            "ws", [{"name": "backend", "path": str(self.backend)}]
        )
        self.assertEqual(selected, [])

    def test_accept_then_select_includes_both_justifications(self) -> None:
        obj = ca.propose(
            self.backend,
            content="Use uv, not pip.",
            justification="Avoid mixed envs",
            title="Deps",
        )
        ca.accept(self.backend, obj["id"])
        selected = ca.select_for_workspace(
            "ws", [{"name": "backend", "path": str(self.backend)}]
        )
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["justification"], "Avoid mixed envs")
        self.assertIn("unconditional", selected[0]["justification_trail"][0])

    def test_reject_blocks_further_transition_and_selection(self) -> None:
        obj = ca.propose(self.backend, content="maybe wrong", justification="guess")
        ca.reject(self.backend, obj["id"])
        self.assertEqual(
            ca.select_for_workspace("ws", [{"name": "backend", "path": str(self.backend)}]), []
        )
        with self.assertRaises(SystemExit):
            ca.accept(self.backend, obj["id"])

    def test_retire_removes_from_selection(self) -> None:
        obj = ca.propose(self.backend, content="stale fact", justification="was true once")
        ca.accept(self.backend, obj["id"])
        ca.retire(self.backend, obj["id"])
        self.assertEqual(
            ca.select_for_workspace("ws", [{"name": "backend", "path": str(self.backend)}]), []
        )
        with self.assertRaises(SystemExit):
            ca.retire(self.backend, obj["id"])  # already retired

    def test_accept_can_edit_content_and_applicability(self) -> None:
        obj = ca.propose(self.backend, content="original", justification="j")
        ca.accept(
            self.backend,
            obj["id"],
            edited_content="corrected",
            edited_applicability={"workspace": "ws-a"},
        )
        matched = ca.select_for_workspace(
            "ws-a", [{"name": "backend", "path": str(self.backend)}]
        )
        self.assertEqual(matched[0]["content"], "corrected")
        not_matched = ca.select_for_workspace(
            "ws-b", [{"name": "backend", "path": str(self.backend)}]
        )
        self.assertEqual(not_matched, [])

    # -- the RFC's core example: same repos, different truth per workspace --

    def test_workspace_atom_distinguishes_same_repo_set_across_workspaces(self) -> None:
        obj = ca.propose(
            self.contracts,
            content="contracts follow team A's versioning policy",
            justification="team A owns this contract in workspace A",
            applicability={"workspace": ["workspace-a"]},
        )
        ca.accept(self.contracts, obj["id"])

        in_a = ca.select_for_workspace(
            "workspace-a",
            [
                {"name": "backend", "path": str(self.backend)},
                {"name": "contracts", "path": str(self.contracts)},
            ],
        )
        in_b = ca.select_for_workspace(
            "workspace-b",
            [
                {"name": "backend", "path": str(self.backend)},
                {"name": "mobile", "path": str(self.mobile)},
                {"name": "contracts", "path": str(self.contracts)},
            ],
        )
        self.assertEqual(len(in_a), 1)
        self.assertEqual(in_b, [])

    # -- applicability atoms --------------------------------------------------

    def test_repo_set_all_of(self) -> None:
        obj = ca.propose(
            self.contracts,
            content="pair backend+mobile rule",
            justification="j",
            applicability={"repo_set_all_of": ["backend", "mobile"]},
        )
        ca.accept(self.contracts, obj["id"])

        with_both = ca.select_for_workspace(
            "ws",
            [
                {"name": "backend", "path": str(self.backend)},
                {"name": "mobile", "path": str(self.mobile)},
                {"name": "contracts", "path": str(self.contracts)},
            ],
        )
        with_only_backend = ca.select_for_workspace(
            "ws",
            [
                {"name": "backend", "path": str(self.backend)},
                {"name": "contracts", "path": str(self.contracts)},
            ],
        )
        self.assertEqual(len(with_both), 1)
        self.assertEqual(with_only_backend, [])

    def test_repo_set_none_of_excludes(self) -> None:
        obj = ca.propose(
            self.contracts,
            content="only when mobile is absent",
            justification="j",
            applicability={"repo_set_none_of": ["mobile"]},
        )
        ca.accept(self.contracts, obj["id"])

        without_mobile = ca.select_for_workspace(
            "ws", [{"name": "contracts", "path": str(self.contracts)}]
        )
        with_mobile = ca.select_for_workspace(
            "ws",
            [
                {"name": "contracts", "path": str(self.contracts)},
                {"name": "mobile", "path": str(self.mobile)},
            ],
        )
        self.assertEqual(len(without_mobile), 1)
        self.assertEqual(with_mobile, [])

    def test_branch_glob(self) -> None:
        subprocess.run(
            ["git", "checkout", "-b", "release/1.0"],
            cwd=self.backend,
            check=True,
            capture_output=True,
        )
        obj = ca.propose(
            self.backend,
            content="release freeze rules apply",
            justification="j",
            applicability={"repo_set_any_of": ["backend"], "branch": ["release/*"]},
        )
        ca.accept(self.backend, obj["id"])

        on_release = ca.select_for_workspace(
            "ws", [{"name": "backend", "path": str(self.backend)}]
        )
        self.assertEqual(len(on_release), 1)

        subprocess.run(
            ["git", "checkout", "main"], cwd=self.backend, check=True, capture_output=True
        )
        on_main = ca.select_for_workspace(
            "ws", [{"name": "backend", "path": str(self.backend)}]
        )
        self.assertEqual(on_main, [])

    def test_valid_window(self) -> None:
        obj = ca.propose(
            self.backend,
            content="migration-only note",
            justification="j",
            applicability={"valid_from": "2000-01-01", "valid_until": "2000-01-02"},
        )
        ca.accept(self.backend, obj["id"])
        # window is long past -> must not match "now"
        self.assertEqual(
            ca.select_for_workspace("ws", [{"name": "backend", "path": str(self.backend)}]), []
        )

    def test_unknown_applicability_key_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            ca.propose(
                self.backend,
                content="x",
                justification="j",
                applicability={"totally_made_up": ["x"]},
            )

    # -- selection scoping / cap --------------------------------------------

    def test_select_only_considers_anchors_present_in_workspace(self) -> None:
        b = ca.propose(self.backend, content="b-fact", justification="j")
        ca.accept(self.backend, b["id"])
        m = ca.propose(self.mobile, content="m-fact", justification="j")
        ca.accept(self.mobile, m["id"])

        only_backend = ca.select_for_workspace(
            "ws", [{"name": "backend", "path": str(self.backend)}]
        )
        self.assertEqual([i["id"] for i in only_backend], [b["id"]])

    def test_select_respects_limit(self) -> None:
        for i in range(5):
            obj = ca.propose(self.backend, content=f"fact {i}", justification="j")
            ca.accept(self.backend, obj["id"])
        selected = ca.select_for_workspace(
            "ws", [{"name": "backend", "path": str(self.backend)}], limit=2
        )
        self.assertEqual(len(selected), 2)

    # -- storage --------------------------------------------------------------

    def test_store_is_git_versioned_per_anchor(self) -> None:
        obj = ca.propose(self.backend, content="x", justification="j")
        store_dir = ca.project_store_dir(self.backend, ensure=False)
        self.assertTrue((store_dir / ".git").is_dir())
        log = ca.run_git(store_dir, "log", "--oneline")
        self.assertIn(obj["id"][:6], log.stdout)

    def test_anchor_does_not_leak_across_projects_with_no_applicability(self) -> None:
        """RFC-0001 v2's core fix: an unconditional assertion is scoped by
        which *anchor* is present in the workspace, not by any workspace name."""
        obj = ca.propose(self.contracts, content="contracts default note", justification="j")
        ca.accept(self.contracts, obj["id"])

        workspace_without_contracts = ca.select_for_workspace(
            "ws", [{"name": "backend", "path": str(self.backend)}]
        )
        workspace_with_contracts = ca.select_for_workspace(
            "ws", [{"name": "contracts", "path": str(self.contracts)}]
        )
        self.assertEqual(workspace_without_contracts, [])
        self.assertEqual(len(workspace_with_contracts), 1)

    # -- RFC-0002: epistemic_status / criticality / relations ----------------

    def test_defaults_are_fact_and_normal(self) -> None:
        obj = ca.propose(self.backend, content="x", justification="j")
        self.assertEqual(obj["epistemic_status"], "fact")
        self.assertEqual(obj["criticality"], "normal")
        self.assertEqual(obj["relations"], [])

    def test_invalid_epistemic_status_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            ca.propose(self.backend, content="x", justification="j", epistemic_status="guess")

    def test_invalid_criticality_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            ca.propose(self.backend, content="x", justification="j", criticality="urgent")

    def test_valid_epistemic_status_and_criticality_roundtrip(self) -> None:
        obj = ca.propose(
            self.backend, content="x", justification="j",
            epistemic_status="hypothesis", criticality="high",
        )
        self.assertEqual(obj["epistemic_status"], "hypothesis")
        self.assertEqual(obj["criticality"], "high")

    def test_relation_requires_existing_target(self) -> None:
        with self.assertRaises(SystemExit):
            ca.propose(
                self.backend, content="x", justification="j",
                relations=[{"type": "depends_on", "target_id": "nope", "target_project": str(self.contracts)}],
            )

    def test_relation_rejects_unknown_type(self) -> None:
        target = ca.propose(self.contracts, content="t", justification="j")
        ca.accept(self.contracts, target["id"])
        with self.assertRaises(SystemExit):
            ca.propose(
                self.backend, content="x", justification="j",
                relations=[{"type": "made_up", "target_id": target["id"], "target_project": str(self.contracts)}],
            )

    def test_relation_valid_roundtrip(self) -> None:
        target = ca.propose(self.contracts, content="t", justification="j")
        ca.accept(self.contracts, target["id"])
        obj = ca.propose(
            self.backend, content="x", justification="j",
            relations=[{"type": "depends_on", "target_id": target["id"], "target_project": str(self.contracts)}],
        )
        self.assertEqual(len(obj["relations"]), 1)
        self.assertEqual(obj["relations"][0]["type"], "depends_on")
        self.assertEqual(obj["relations"][0]["target_id"], target["id"])

    def test_accept_can_edit_epistemic_status_criticality_relations(self) -> None:
        target = ca.propose(self.contracts, content="t", justification="j")
        ca.accept(self.contracts, target["id"])
        obj = ca.propose(self.backend, content="x", justification="j")
        accepted = ca.accept(
            self.backend, obj["id"],
            edited_epistemic_status="hypothesis",
            edited_criticality="high",
            edited_relations=[{"type": "risk_of", "target_id": target["id"], "target_project": str(self.contracts)}],
        )
        self.assertEqual(accepted["epistemic_status"], "hypothesis")
        self.assertEqual(accepted["criticality"], "high")
        self.assertEqual(accepted["relations"][0]["type"], "risk_of")

    # -- RFC-0002: bounded 1-hop relation traversal in the Applicability Layer --

    def test_relation_target_pulled_in_when_its_project_is_mounted(self) -> None:
        # Applicability scoped to a workspace that isn't "ws" — this target
        # must NOT match directly; only relation traversal should surface it.
        target = ca.propose(
            self.contracts, content="risk note", justification="j",
            applicability={"workspace": ["some-other-workspace"]},
        )
        ca.accept(self.contracts, target["id"])
        source = ca.propose(
            self.backend, content="depends on contracts behaviour", justification="j",
            relations=[{"type": "depends_on", "target_id": target["id"], "target_project": str(self.contracts)}],
        )
        ca.accept(self.backend, source["id"])

        selected = ca.select_for_workspace(
            "ws",
            [
                {"name": "backend", "path": str(self.backend)},
                {"name": "contracts", "path": str(self.contracts)},
            ],
        )
        ids = {i["id"] for i in selected}
        self.assertIn(source["id"], ids)
        self.assertIn(target["id"], ids)
        pulled = next(i for i in selected if i["id"] == target["id"])
        self.assertIn("pulled in via depends_on", pulled["justification_trail"][0])

    def test_relation_target_not_pulled_in_when_its_project_is_absent(self) -> None:
        target = ca.propose(self.contracts, content="risk note", justification="j")
        ca.accept(self.contracts, target["id"])
        source = ca.propose(
            self.backend, content="depends on contracts behaviour", justification="j",
            relations=[{"type": "depends_on", "target_id": target["id"], "target_project": str(self.contracts)}],
        )
        ca.accept(self.backend, source["id"])

        # contracts is NOT part of this workspace — its assertion must not leak in.
        selected = ca.select_for_workspace("ws", [{"name": "backend", "path": str(self.backend)}])
        ids = {i["id"] for i in selected}
        self.assertIn(source["id"], ids)
        self.assertNotIn(target["id"], ids)

    def test_relation_traversal_is_bounded_to_one_hop(self) -> None:
        # a -> depends_on -> b -> depends_on -> c ; only a and b should be
        # pulled in when only "a" matches applicability directly. b and c are
        # scoped out of direct matching so the only path to either is via
        # relations from a matched item.
        out_of_scope = {"workspace": ["some-other-workspace"]}
        c = ca.propose(self.mobile, content="c", justification="j", applicability=out_of_scope)
        ca.accept(self.mobile, c["id"])
        b = ca.propose(
            self.contracts, content="b", justification="j", applicability=out_of_scope,
            relations=[{"type": "depends_on", "target_id": c["id"], "target_project": str(self.mobile)}],
        )
        ca.accept(self.contracts, b["id"])
        a = ca.propose(
            self.backend, content="a", justification="j",
            relations=[{"type": "depends_on", "target_id": b["id"], "target_project": str(self.contracts)}],
        )
        ca.accept(self.backend, a["id"])

        selected = ca.select_for_workspace(
            "ws",
            [
                {"name": "backend", "path": str(self.backend)},
                {"name": "contracts", "path": str(self.contracts)},
                {"name": "mobile", "path": str(self.mobile)},
            ],
        )
        ids = {i["id"] for i in selected}
        self.assertIn(a["id"], ids)
        self.assertIn(b["id"], ids)
        self.assertNotIn(c["id"], ids)  # two hops away — must not be pulled in

    def test_relation_traversal_respects_limit(self) -> None:
        targets = []
        for i in range(5):
            t = ca.propose(self.contracts, content=f"t{i}", justification="j")
            ca.accept(self.contracts, t["id"])
            targets.append(t)
        source = ca.propose(
            self.backend, content="source", justification="j",
            relations=[
                {"type": "depends_on", "target_id": t["id"], "target_project": str(self.contracts)}
                for t in targets
            ],
        )
        ca.accept(self.backend, source["id"])

        selected = ca.select_for_workspace(
            "ws",
            [
                {"name": "backend", "path": str(self.backend)},
                {"name": "contracts", "path": str(self.contracts)},
            ],
            limit=3,
        )
        self.assertEqual(len(selected), 3)

    def test_relation_target_that_is_later_retired_is_not_pulled_in(self) -> None:
        target = ca.propose(self.contracts, content="risk note", justification="j")
        ca.accept(self.contracts, target["id"])
        source = ca.propose(
            self.backend, content="depends on contracts behaviour", justification="j",
            relations=[{"type": "depends_on", "target_id": target["id"], "target_project": str(self.contracts)}],
        )
        ca.accept(self.backend, source["id"])
        ca.retire(self.contracts, target["id"])

        selected = ca.select_for_workspace(
            "ws",
            [
                {"name": "backend", "path": str(self.backend)},
                {"name": "contracts", "path": str(self.contracts)},
            ],
        )
        ids = {i["id"] for i in selected}
        self.assertIn(source["id"], ids)
        self.assertNotIn(target["id"], ids)


if __name__ == "__main__":
    unittest.main()
