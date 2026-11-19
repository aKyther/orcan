"""Only matching owned, unclaimed ancestor checks may be superseded atomically."""

import fcntl
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import commit

from orcan_executor import engine, notifications, retention, store
from orcan_executor.settings import state_dir


def submit(repo, *, owner="", group="task-build", **kwargs):
    return engine.submit(
        repo,
        "HEAD",
        "build",
        "quality",
        [],
        30,
        replace_pending=group,
        replace_owner=owner,
        **kwargs,
    )


def advance(repo):
    (repo / "revision.txt").write_text(uuid4().hex)
    commit(repo)


def test_replacement_releases_full_queue_and_keeps_history_and_ref(repo, monkeypatch):
    monkeypatch.setenv("ORCAN_EXECUTOR_MAX_PENDING", "1")
    old = submit(repo)
    advance(repo)
    new = submit(repo)
    cancelled = store.get(old["id"])
    assert cancelled["status"] == "cancelled"
    assert cancelled["superseded_by"] == new["id"]
    assert cancelled["attempts"] == 0 and cancelled["summary"]["tests"] == 0
    assert "seconds" not in cancelled["summary"]  # No invented execution duration.
    assert new["id"] in notifications.message(cancelled)
    assert new["superseded_count"] == 1
    assert engine.run_job(old["id"]) is None
    assert engine.git(repo, "rev-parse", "refs/orcan/executor/jobs/" + old["id"]) == old["sha"]
    assert store.board()["stats"]["superseded_jobs"] == 1
    with store.database() as db:
        db.execute(
            "UPDATE jobs SET finished=? WHERE id=?",
            ((datetime.now(UTC) - timedelta(hours=2)).isoformat(), old["id"]),
        )
    assert retention.prune() == 1
    assert store.get(old["id"])["superseded_by"] == new["id"]
    assert engine.run_job(old["id"]) is None
    assert not (state_dir() / "jobs" / old["id"]).exists()


@pytest.mark.parametrize(
    "protected", ["running", "claimed", "other-owner", "shared", "other-group"]
)
def test_protected_work_is_never_replaced(repo, protected):
    owner = str(uuid4())
    old = submit(repo, owner=owner)
    advance(repo)
    handle = None
    try:
        if protected == "running":
            assert store.start(old["id"], repo / "fixture")
        elif protected == "claimed":
            directory = state_dir() / "jobs" / old["id"]
            directory.mkdir(parents=True)
            handle = (directory / "run.lock").open("a")
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        elif protected == "shared":
            notifications.register(old["id"], str(uuid4()))
        new = submit(
            repo,
            owner=str(uuid4()) if protected == "other-owner" else owner,
            group="other-task" if protected == "other-group" else "task-build",
        )
        assert new["superseded_count"] == 0
        assert store.get(old["id"])["status"] == ("running" if protected == "running" else "queued")
    finally:
        if handle:
            handle.close()


def test_older_or_identical_sha_cannot_replace_newer_work(repo):
    base = engine.git(repo, "rev-parse", "HEAD")
    advance(repo)
    old = submit(repo)
    assert submit(repo)["superseded_count"] == 0
    earlier = engine.submit(repo, base, "older", "quality", [], 30, replace_pending="task-build")
    assert earlier["superseded_count"] == 0
    assert store.get(old["id"])["status"] == "queued"


def test_changed_timeout_does_not_cancel_a_different_scope(repo):
    old = submit(repo)
    advance(repo)
    new = engine.submit(repo, "HEAD", "build", "quality", [], 60, replace_pending="task-build")
    assert new["superseded_count"] == 0
    assert store.get(old["id"])["status"] == "queued"


def test_capacity_rejection_cannot_cancel_running_work_or_leave_new_pin(repo, monkeypatch):
    monkeypatch.setenv("ORCAN_EXECUTOR_MAX_PENDING", "1")
    old = submit(repo)
    assert store.start(old["id"], repo / "fixture")
    advance(repo)
    with pytest.raises(ValueError, match="capacity"):
        submit(repo)
    assert store.get(old["id"])["status"] == "running"
    assert len(engine.git(repo, "for-each-ref", "refs/orcan/executor/jobs").splitlines()) == 1


def test_divergent_branch_does_not_replace_another_branch(repo):
    base = engine.git(repo, "rev-parse", "HEAD")
    advance(repo)
    old = submit(repo)
    engine.git(repo, "checkout", "-qb", "divergent-fixture", base)
    advance(repo)
    assert submit(repo)["superseded_count"] == 0
    assert store.get(old["id"])["status"] == "queued"


def test_concurrent_replacements_never_cancel_the_newest_revision(repo):
    old = submit(repo)
    advance(repo)
    intermediate = engine.git(repo, "rev-parse", "HEAD")
    advance(repo)
    latest = engine.git(repo, "rev-parse", "HEAD")

    def request(sha):
        return engine.submit(repo, sha, "race", "quality", [], 30, replace_pending="task-build")

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(request, [intermediate, latest]))
    assert store.get(old["id"])["status"] == "cancelled"
    assert store.get(results[1]["id"])["status"] == "queued"
    assert store.get(results[1]["id"])["sha"] == latest


def test_replacement_requires_an_explicit_valid_group_and_disallows_reuse(repo):
    for group in ("", "task with spaces", "x" * 81):
        with pytest.raises(ValueError, match="Replacement requires"):
            submit(repo, group=group)
    with pytest.raises(ValueError, match="cannot combine"):
        submit(repo, reuse=True)
    assert engine.git(repo, "for-each-ref", "refs/orcan/executor/jobs") == ""


@pytest.mark.parametrize("scope", ["selectors", "profile", "lane"])
def test_other_profile_test_scope_or_lane_is_preserved(repo, scope, monkeypatch):
    monkeypatch.setenv("ORCAN_EXECUTOR_SPLIT_LANES", "1")
    profile, selectors = ("selected", ["TestA"]) if scope == "selectors" else ("quality", [])
    old = engine.submit(repo, "HEAD", "scope", profile, selectors, 30, replace_pending="scope")
    if scope == "lane":
        path = repo / ".orcan/checks.json"
        config = json.loads(path.read_text())
        config["profiles"][profile]["lane"] = "heavy"
        path.write_text(json.dumps(config))
    advance(repo)
    if scope == "selectors":
        selectors = ["TestB"]
    elif scope == "profile":
        profile, selectors = "selected", ["TestA"]
    new = engine.submit(repo, "HEAD", "scope", profile, selectors, 30, replace_pending="scope")
    assert new["superseded_count"] == 0
    assert store.get(old["id"])["status"] == "queued"
