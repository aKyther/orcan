"""Bulk parent updates against local remotes; never contact real projects or providers."""

import fcntl
import json
import os
import subprocess
from pathlib import Path

import pytest

from ._scripts_loader import load_script

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
puller = load_script("sandbox-pull.py")


def run(*args, cwd=None):
    return subprocess.run(
        list(args), cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def project(tmp_path, name="project"):
    remote = tmp_path / "remotes" / (name + ".git")
    writer = tmp_path / "writers" / name
    parent = tmp_path / "sandbox" / name
    remote.parent.mkdir(parents=True, exist_ok=True)
    writer.parent.mkdir(parents=True, exist_ok=True)
    parent.parent.mkdir(parents=True, exist_ok=True)
    run("git", "init", "--bare", "-q", "--initial-branch=main", str(remote))
    run("git", "clone", "-q", str(remote), str(writer))
    run("git", "config", "user.name", "Fixture", cwd=writer)
    run("git", "config", "user.email", "fixture@example.invalid", cwd=writer)
    (writer / "tracked.txt").write_text("original\n")
    run("git", "add", ".", cwd=writer)
    run("git", "commit", "-qm", "initial", cwd=writer)
    run("git", "push", "-qu", "origin", "main", cwd=writer)
    run("git", "clone", "-q", str(remote), str(parent))
    return parent, writer


def advance(writer):
    with (writer / "tracked.txt").open("a") as stream:
        stream.write("remote addition\n")
    run("git", "commit", "-qam", "advance", cwd=writer)
    run("git", "push", "-q", cwd=writer)
    return run("git", "rev-parse", "HEAD", cwd=writer)


def invoke(tmp_path, *args):
    proc = subprocess.run(
        [
            "bash",
            str(ROOT / "bin/orcan"),
            "sandbox",
            "pull",
            "--root",
            str(tmp_path / "sandbox"),
            "--json",
            *args,
        ],
        env={**os.environ, "ORCAN_HOME": str(tmp_path / "home")},
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return proc, json.loads(proc.stdout)


def test_bulk_pull_updates_nested_parents_and_leaves_all_worktrees_untouched(tmp_path):
    parent, writer = project(tmp_path, "group/project")
    worktree = tmp_path / "sandbox/.worktrees/task"
    run("git", "-C", str(parent), "worktree", "add", "-b", "task", str(worktree))
    linked = tmp_path / "sandbox/visible-task"
    run("git", "-C", str(parent), "worktree", "add", "-b", "visible-task", str(linked))
    old = run("git", "rev-parse", "HEAD", cwd=worktree)
    (worktree / "tracked.txt").write_text("agent's uncommitted edit\n")
    expected = advance(writer)
    proc, result = invoke(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert result["counts"]["updated"] == 1
    assert result["counts"]["skipped"] == 1
    assert run("git", "rev-parse", "HEAD", cwd=parent) == expected
    assert run("git", "rev-parse", "HEAD", cwd=worktree) == old
    assert run("git", "rev-parse", "HEAD", cwd=linked) == old
    assert (worktree / "tracked.txt").read_text() == "agent's uncommitted edit\n"
    assert not any(".worktrees" in item["path"] for item in result["results"])


@pytest.mark.parametrize("change", ["tracked", "untracked"])
def test_dirty_parent_is_skipped_without_stashing_or_touching_files(tmp_path, change):
    parent, writer = project(tmp_path)
    before = run("git", "rev-parse", "HEAD", cwd=parent)
    advance(writer)
    dirty = parent / ("tracked.txt" if change == "tracked" else "new.txt")
    dirty.write_text("KEEP MY WORK")
    proc, result = invoke(tmp_path)
    assert proc.returncode == 0
    assert result["counts"]["skipped"] == 1
    assert run("git", "rev-parse", "HEAD", cwd=parent) == before
    assert dirty.read_text() == "KEEP MY WORK"
    assert not run("git", "stash", "list", cwd=parent)


def test_dry_run_does_not_fetch_update_refs_or_create_lock(tmp_path):
    parent, writer = project(tmp_path)
    head = run("git", "rev-parse", "HEAD", cwd=parent)
    advance(writer)
    proc, result = invoke(tmp_path, "--dry-run")
    assert proc.returncode == 0
    assert result["counts"]["would_pull"] == 1
    assert run("git", "rev-parse", "HEAD", cwd=parent) == head
    assert run("git", "rev-parse", "refs/remotes/origin/main", cwd=parent) == head
    assert not (parent / ".git/orcan-sandbox-pull.lock").exists()


def test_divergent_parent_errors_without_merge_and_other_repositories_continue(
    tmp_path,
):
    bad, writer = project(tmp_path, "a-diverged")
    good, other = project(tmp_path, "b-good")
    run("git", "config", "user.name", "Fixture", cwd=bad)
    run("git", "config", "user.email", "fixture@example.invalid", cwd=bad)
    (bad / "local.txt").write_text("local commit")
    run("git", "add", ".", cwd=bad)
    run("git", "commit", "-qm", "local", cwd=bad)
    before = run("git", "rev-parse", "HEAD", cwd=bad)
    advance(writer)
    expected = advance(other)
    proc, result = invoke(tmp_path)
    assert proc.returncode == 1
    assert result["counts"]["error"] == result["counts"]["updated"] == 1
    assert run("git", "rev-parse", "HEAD", cwd=bad) == before
    assert run("git", "rev-parse", "HEAD", cwd=good) == expected
    assert not (bad / ".git/MERGE_HEAD").exists()


@pytest.mark.parametrize("mode", ["detached", "no-upstream", "operation", "busy"])
def test_ineligible_parent_is_skipped(tmp_path, mode):
    parent, _ = project(tmp_path)
    lock = None
    try:
        if mode == "detached":
            run("git", "checkout", "-q", "--detach", cwd=parent)
        elif mode == "no-upstream":
            run("git", "branch", "--unset-upstream", cwd=parent)
        elif mode == "operation":
            (parent / ".git/CHERRY_PICK_HEAD").write_text("a" * 40)
        else:
            lock = (parent / ".git/orcan-sandbox-pull.lock").open("a")
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        proc, result = invoke(tmp_path)
        assert proc.returncode == 0
        assert result["counts"]["skipped"] == 1
    finally:
        if lock:
            lock.close()


def test_scan_ignores_symlinks_bare_repos_hidden_dirs_and_excluded_names(tmp_path):
    root = tmp_path / "sandbox"
    root.mkdir()
    outside, _ = project(tmp_path / "outside")
    (root / "link").symlink_to(outside, target_is_directory=True)
    (root / "external mount/nested").mkdir(parents=True)
    (root / ".worktrees/private").mkdir(parents=True)
    run("git", "init", "--bare", "-q", str(root / "bare.git"))
    proc, result = invoke(tmp_path, "--exclude", "external*")
    assert proc.returncode == 0
    assert len(result["results"]) == 1
    assert result["results"][0]["reason"] == "Bare repository"


def test_configured_root_is_used_without_runtime_env_file(tmp_path, monkeypatch):
    config = tmp_path / "orcan.config.json"
    root = tmp_path / "custom-projects"
    root.mkdir()
    config.write_text(json.dumps({"projects_root": str(root)}))
    monkeypatch.delenv("ORCAN_PROJECTS_ROOT", raising=False)
    monkeypatch.setenv("ORCAN_CONFIG_FILE", str(config))
    assert puller.sandbox_root(None) == root


def test_pull_timeout_is_an_error_and_diagnostics_are_not_dumped(tmp_path, monkeypatch):
    parent, _ = project(tmp_path)
    original = puller.git

    def timeout(path, *args, **kwargs):
        if args and args[0] == "pull":
            raise puller.GitError("private URL/token must not leak")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(puller, "git", timeout)
    result = puller.update(parent, False, 1, set())
    assert result["status"] == "error"
    assert "private" not in json.dumps(result)


def test_public_help_works_without_docker(tmp_path):
    proc = subprocess.run(
        ["bash", str(ROOT / "bin/orcan"), "sandbox", "--help"],
        env={**os.environ, "ORCAN_HOME": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "--dry-run" in proc.stdout and "--exclude" in proc.stdout
