"""Pure partial-outcome contracts, with no Git or CLI subprocesses."""

from ._scripts_loader import load_script

worktree = load_script("studio-worktree.py")


def test_partial_bind_preserves_completed_steps_and_pending_order(
    monkeypatch, tmp_path
):
    calls = []

    def run(command):
        calls.append(command)
        failed = command[-1] == "second"
        return worktree.subprocess.CompletedProcess(
            command, int(failed), "", "blocked" if failed else ""
        )

    monkeypatch.setattr(worktree, "run_command", run)
    report = worktree.apply_worktree(
        tmp_path / "repo",
        "feature",
        tmp_path / "tree",
        ["first", "second", "third"],
        "repo--feature",
    )
    assert report["ok"] is True
    assert report["outcome"] == "partial"
    assert report["result"]["completed"] == ["worktree created", "attached to first"]
    assert report["result"]["pending_workspaces"] == ["second", "third"]
    assert report["result"]["retry"] == "attachments_only"
    assert len(calls) == 2
    assert not any("remove" in command for command in calls)


def test_failure_before_creation_is_not_resumable(monkeypatch, tmp_path):
    monkeypatch.setattr(
        worktree,
        "run_command",
        lambda command: worktree.subprocess.CompletedProcess(command, 1, "", "blocked"),
    )
    report = worktree.apply_worktree(
        tmp_path / "repo", "feature", tmp_path / "absent", ["first"], "repo--feature"
    )
    assert report == {"ok": False, "error": "blocked"}


def test_creation_then_first_attachment_failure_requires_verified_worktree(
    monkeypatch, tmp_path
):
    destination = tmp_path / "tree"
    destination.mkdir()
    monkeypatch.setattr(
        worktree,
        "run_command",
        lambda command: worktree.subprocess.CompletedProcess(
            command, 1, "", "bind failed"
        ),
    )
    monkeypatch.setattr(worktree, "verified_worktree", lambda *args: True)
    report = worktree.apply_worktree(
        tmp_path / "repo", "feature", destination, ["first"], "repo--feature"
    )
    assert report["result"]["pending_workspaces"] == ["first"]
    monkeypatch.setattr(worktree, "verified_worktree", lambda *args: False)
    assert (
        worktree.apply_worktree(
            tmp_path / "repo", "feature", destination, ["first"], "repo--feature"
        )["ok"]
        is False
    )
