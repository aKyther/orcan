"""Fork selection uses real Git fixtures; GitHub discovery stays offline."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/repository"))

import fork_worktrees as fw
import git_worktrees as gw
from workspace_draft import WorkspaceDraft


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.mark.parametrize(
    "source",
    [
        "alice:",
        ":topic",
        "alice:../bad",
        "alice:topic:bad",
        "alice:-bad",
        "alice:bad.lock",
        "alice:foo//bar",
    ],
)
@pytest.mark.integration
def test_invalid_source(source):
    with pytest.raises(fw.ForkSourceError):
        fw.worktree_branch(source)


@pytest.mark.integration
def test_source_names_separate_owners_and_local_branches():
    assert fw.worktree_branch("Alice:fix/login") == "fork/alice/fix/login"
    assert fw.worktree_branch("bob:fix/login") == "fork/bob/fix/login"
    assert fw.worktree_branch("fix/login") == "fix/login"


@pytest.mark.parametrize(
    "url,clone",
    [
        ("git@github.com:upstream/app.git", "git@github.com:alice/renamed.git"),
        ("https://github.com/upstream/app.git", "https://github.com/alice/renamed.git"),
        ("ssh://git@github.com/upstream/app.git", "git@github.com:alice/renamed.git"),
    ],
)
def test_resolve_renamed_fork_across_pages(url, clone):
    base = {"full_name": "upstream/app", "owner": {"login": "upstream"}}
    fork = {"full_name": "alice/renamed", "owner": {"login": "Alice"}}
    with (
        patch.object(fw, "_git", return_value=url),
        patch.object(fw, "_api", side_effect=[base, [[], [fork]]]) as api,
    ):
        assert fw.resolve_fork(Path("/unused"), "alice") == ("alice/renamed", clone)
    assert api.call_args.args[1] == "repos/upstream/app/forks?per_page=100"


def test_resolves_from_fork_origin_via_network_source():
    base = {
        "full_name": "bob/app",
        "owner": {"login": "bob"},
        "source": {"full_name": "upstream/app"},
    }
    with (
        patch.object(fw, "_git", return_value="https://github.com/bob/app"),
        patch.object(fw, "_api", side_effect=[base, [[]]]) as api,
    ):
        with pytest.raises(fw.ForkSourceError, match="found 0"):
            fw.resolve_fork(Path("/unused"), "alice")
    assert api.call_args.args[1] == "repos/upstream/app/forks?per_page=100"


def test_ambiguous_fork_is_rejected():
    base = {"full_name": "upstream/app", "owner": {"login": "upstream"}}
    fork = {"full_name": "alice/app", "owner": {"login": "alice"}}
    with (
        patch.object(fw, "_git", return_value="https://github.com/upstream/app"),
        patch.object(fw, "_api", side_effect=[base, [[fork, fork]]]),
    ):
        with pytest.raises(fw.ForkSourceError, match="found 2"):
            fw.resolve_fork(Path("/unused"), "alice")


def test_unsupported_host_does_not_guess():
    with patch.object(fw, "_git", return_value="git@gitlab.com:upstream/app.git"):
        with pytest.raises(fw.ForkSourceError, match="github.com"):
            fw.resolve_fork(Path("/unused"), "alice")


@pytest.mark.parametrize(
    "failure", [FileNotFoundError(), subprocess.TimeoutExpired("gh", 30)]
)
def test_api_unavailable_is_recoverable(failure):
    with patch.object(fw.subprocess, "run", side_effect=failure):
        with pytest.raises(fw.ForkSourceError, match="GitHub CLI"):
            fw._api(Path("/unused"), "repos/upstream/app")


@pytest.fixture
def fork_repos(tmp_path, monkeypatch, tracked_git_repo_factory):
    repo = tmp_path / "main"
    fork = tmp_path / "fork"
    tracked_git_repo_factory(repo)
    subprocess.run(["git", "clone", "--quiet", str(repo), str(fork)], check=True)
    git(fork, "config", "user.email", "fixture@example.invalid")
    git(fork, "config", "user.name", "Fixture")
    git(fork, "checkout", "-b", "fix/login")
    (fork / "fork-change.txt").write_text("fork code\n")
    git(fork, "add", "fork-change.txt")
    git(fork, "commit", "-m", "Fork-only change")
    monkeypatch.setenv("ORCAN_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ORCAN_DATA", str(tmp_path / "home"))
    monkeypatch.setenv("ORCAN_PROJECTS_ROOT", str(tmp_path / "sandbox"))
    monkeypatch.setenv("ORCAN_NAMED_INSTANCE", "")
    monkeypatch.setattr(
        fw, "resolve_fork", lambda *args, **kwargs: ("alice/renamed", str(fork))
    )
    return repo, fork


@pytest.mark.integration
def test_draft_save_fetches_fork_commit_and_tracks_source(fork_repos, tmp_path):
    repo, fork = fork_repos
    original_head = git(repo, "rev-parse", "HEAD")
    original_branch = git(repo, "branch", "--show-current")
    (repo / "local-change.txt").write_text("keep me")
    config = tmp_path / "home/orcan.config.json"
    draft = WorkspaceDraft(config)
    ws = draft.add_workspace("review")
    draft.add_projects(ws, [repo])
    ws["projects"][0].update(_mode="worktree", _branch="alice:fix/login")
    draft.validate()
    assert git(repo, "remote") == ""  # Draft validation does not fetch or add remotes.
    draft.save()
    target = Path(
        json.loads(config.read_text())["workspaces"][0]["projects"][0]["path"]
    )
    assert git(target, "rev-parse", "HEAD") == git(fork, "rev-parse", "HEAD")
    assert git(target, "branch", "--show-current") == "fork/alice/fix/login"
    assert (
        git(target, "rev-parse", "--abbrev-ref", "@{upstream}")
        == "orcan-fork-alice/fix/login"
    )
    assert (target / "fork-change.txt").read_text() == "fork code\n"
    assert git(repo, "rev-parse", "HEAD") == original_head
    assert git(repo, "branch", "--show-current") == original_branch
    assert (repo / "local-change.txt").read_text() == "keep me"
    assert gw.load_manifest()[0].branch == "fork/alice/fix/login"


@pytest.mark.integration
def test_missing_branch_never_falls_back_to_head(fork_repos, tmp_path):
    repo, _ = fork_repos
    dest = tmp_path / "checkout"
    with pytest.raises(gw.WorktreeCreateError, match="Could not fetch"):
        gw.create_worktree(repo, branch="alice:missing", path=dest, fatal=False)
    assert not dest.exists()
    assert not gw.branch_exists(repo, "fork/alice/missing")


@pytest.mark.integration
def test_existing_remote_is_not_overwritten(fork_repos, tmp_path):
    repo, _ = fork_repos
    git(repo, "remote", "add", "orcan-fork-alice", "/somewhere/else")
    with pytest.raises(gw.WorktreeCreateError, match="points elsewhere"):
        gw.create_worktree(
            repo, branch="alice:fix/login", path=tmp_path / "checkout", fatal=False
        )
    assert git(repo, "remote", "get-url", "orcan-fork-alice") == "/somewhere/else"


@pytest.mark.integration
def test_existing_local_fork_branch_is_not_silently_reused(fork_repos, tmp_path):
    repo, _ = fork_repos
    git(repo, "branch", "fork/alice/fix/login")
    with pytest.raises(gw.WorktreeCreateError, match="already exists"):
        gw.create_worktree(
            repo, branch="alice:fix/login", path=tmp_path / "checkout", fatal=False
        )


@pytest.mark.integration
def test_retry_after_config_failure_preserves_created_checkout(fork_repos, tmp_path):
    repo, _ = fork_repos
    draft = WorkspaceDraft(tmp_path / "home/orcan.config.json")
    ws = draft.add_workspace("review")
    draft.add_projects(ws, [repo])
    ws["projects"][0].update(_mode="worktree", _branch="alice:fix/login")
    with patch("workspace_draft.dump_config", side_effect=OSError("fixture failure")):
        with pytest.raises(OSError, match="fixture failure"):
            draft.save()
    assert len(draft.created) == 1
    draft.save()
    assert len(gw.list_worktrees(repo)) == 2
