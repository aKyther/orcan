"""In-process Git inspection contracts: failures are never clean checkouts."""

import json
import pytest
from types import SimpleNamespace

from ._scripts_loader import load_script

probe = load_script("studio-probe.py")
parent = load_script("studio-parent.py")


@pytest.mark.parametrize(
    "status,branch,dirty,ahead,behind",
    [
        (
            "# branch.head main\n# branch.upstream origin/main\n# branch.ab +2 -3",
            "main",
            False,
            2,
            3,
        ),
        ("# branch.head main\n? untracked.txt", "main", True, None, None),
        ("# branch.head (detached)", None, False, None, None),
        ("# branch.head main\n# branch.ab invalid", "main", False, None, None),
        (None, None, None, None, None),
    ],
)
def test_git_facts_share_one_status_snapshot(
    tmp_path, monkeypatch, status, branch, dirty, ahead, behind
):
    calls = []

    def output(path, *args):
        calls.append(args)
        return {"rev-parse": ".git", "status": status, "config": "origin"}.get(args[0])

    monkeypatch.setattr(probe, "git_output", output)
    facts = probe.git_details(tmp_path)
    assert (facts["branch"], facts["dirty"], facts["ahead"], facts["behind"]) == (
        branch,
        dirty,
        ahead,
        behind,
    )
    assert [args[0] for args in calls] == ["rev-parse", "status", "config"]


def test_unknown_probe_status_blocks_parent_updates(tmp_path, monkeypatch):
    repo = tmp_path / "app"
    (repo / ".git").mkdir(parents=True)
    facts = {"rev-parse": ".git", "config": "origin"}
    monkeypatch.setattr(probe, "git_output", lambda path, *args: facts.get(args[0]))
    config = tmp_path / "orcan.config.json"
    config.write_text(
        json.dumps({"workspaces": [{"name": "dev", "projects": [{"path": str(repo)}]}]})
    )
    snapshot = probe.context_snapshot(config, tmp_path, tmp_path / "index.json")
    project = snapshot["workspaces"][0]["projects"][0]
    assert project["dirty"] is None
    assert project["git_status"] == "unknown"
    assert snapshot["update_targets"] == []


def test_snapshot_classifies_each_path_once_without_sharing_binding_names(
    tmp_path, monkeypatch
):
    repo = tmp_path / "app"
    repo.mkdir()
    calls = []

    def classify(path):
        calls.append(path.resolve())
        return {"path": str(path), "kind": "directory"}

    monkeypatch.setattr(probe, "classify_path", classify)
    config = tmp_path / "orcan.config.json"
    config.write_text(
        json.dumps(
            {
                "workspaces": [
                    {"name": "a", "projects": [{"name": "first", "path": str(repo)}]},
                    {"name": "b", "projects": [{"name": "second", "path": str(repo)}]},
                ]
            }
        )
    )
    result = probe.context_snapshot(config, tmp_path, tmp_path / "index.json")
    assert calls.count(repo.resolve()) == 1
    assert [w["projects"][0]["name"] for w in result["workspaces"]] == [
        "first",
        "second",
    ]
    probe.context_snapshot(config, tmp_path, tmp_path / "index.json")
    assert calls.count(repo.resolve()) == 2  # No persistent stale cache.


def test_parent_plan_rejects_failed_status(tmp_path, monkeypatch):
    def git(path, *args, **kwargs):
        values = {
            "rev-parse": "true",
            "symbolic-ref": "main",
            "ls-remote": "abc refs/heads/main",
        }
        return SimpleNamespace(
            returncode=1 if args[0] == "status" else 0, stdout=values.get(args[0], "")
        )

    monkeypatch.setattr(parent, "git", git)
    plan = parent.inspect(tmp_path, "main")
    assert plan["dirty"] is None
    assert not plan["ready"]
    assert "cannot determine" in plan["blockers"][0]
