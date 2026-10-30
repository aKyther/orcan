"""Recovery must never duplicate work still holding an inherited execution lock."""

import fcntl
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from orcan_executor import cli, diagnostics, engine, store
from orcan_executor.settings import state_dir


def running(repo):
    job = engine.submit(repo, "HEAD", "recovery", "quality", [], 30)
    assert store.start(job["id"], Path("fixture"))
    return job


def test_interrupted_job_requires_explicit_guarded_recovery(repo):
    job = running(repo)
    assert diagnostics.jobs()["interrupted"] == 1
    with engine.recovery_guard(job["id"]):
        value = store.get(job["id"])
        assert value["status"] == "queued"
        assert value["recovery_count"] == 1
        assert diagnostics.jobs()["jobs"][0]["execution_lock"] == "held"
    assert store.get(job["id"])["attempts"] == 1


def test_live_child_inherits_lock_and_blocks_recovery_after_parent_releases(repo):
    job = running(repo)
    directory = state_dir() / "jobs" / job["id"]
    directory.mkdir(parents=True)
    handle = (directory / "run.lock").open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    child = subprocess.Popen(
        [sys.executable, "-c", "import sys; print('ready',flush=True); sys.stdin.read()"],
        pass_fds=(handle.fileno(),),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    try:
        assert child.stdout.readline() == b"ready\n"
        handle.close()
        assert diagnostics.jobs()["interrupted"] == 0
        assert diagnostics.jobs()["jobs"][0]["condition"] == "execution_present"
        with pytest.raises(ValueError, match="still held"):
            with engine.recovery_guard(job["id"]):
                pytest.fail("Recovery entered while a child was alive")
    finally:
        handle.close()
        child.stdin.close()
        child.wait(timeout=5)
        child.stdout.close()
    assert diagnostics.jobs()["interrupted"] == 1


def test_recovery_of_terminal_job_cannot_publish_again(repo, monkeypatch):
    job = engine.submit(repo, "HEAD", "done", "quality", [], 30)
    engine.run_job(job["id"])
    publish = Mock()
    monkeypatch.setattr(cli, "enqueue", publish)
    assert cli.main(["recover", "--job", job["id"]]) == 1
    publish.assert_not_called()


def test_unknown_lock_state_is_not_recovery_evidence(repo, monkeypatch):
    running(repo)
    monkeypatch.setattr(diagnostics, "lock_held", lambda _: None)
    value = diagnostics.jobs()
    assert value["interrupted"] == 0
    assert value["jobs"][0]["condition"] == "unverifiable"
