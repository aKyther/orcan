"""Broker delivery order must not let one repository consume every admission."""

from pathlib import Path
from uuid import uuid4

from orcan_executor import store


def queued(repo, lane="default", *, checkout=None, published=True):
    job = dict(
        id=uuid4().hex,
        repo=checkout or f"/{repo}/checkout",
        git_dir=f"/{repo}/.git",
        sha="a" * 40,
        task="fixture",
        profile="build",
        selectors=[],
        timeout=30,
        lane=lane,
    )
    store.create(job)
    if published:
        store.publication(job["id"], "published")
    return job["id"]


def complete(job):
    store.finish(job, "passed", {"seconds": 1}, Path("fixture-report"))


def test_repo_round_robin_and_fifo_survive_unfair_broker_order(monkeypatch):
    monkeypatch.setenv("ORCAN_EXECUTOR_MAX_RUNNING", "1")
    a = [queued("a") for _ in range(3)]
    b = [queued("b") for _ in range(2)]
    assert store.start(a[0], Path("fixture"))
    complete(a[0])
    assert not store.start(a[2], Path("fixture"))
    assert not store.start(a[1], Path("fixture"))
    assert store.get(a[1])["admission_reason"] == "fair_turn"
    assert store.start(b[0], Path("fixture"))
    complete(b[0])
    assert not store.start(b[1], Path("fixture"))
    assert store.start(a[1], Path("fixture"))
    assert store.get(a[1])["admission_reason"] is None
    complete(a[1])
    assert not store.start(a[2], Path("fixture"))
    assert store.start(b[1], Path("fixture"))
    complete(b[1])
    assert store.start(a[2], Path("fixture"))


def test_worktrees_share_a_turn_but_lanes_are_independent():
    first = queued("common", checkout="/worktree/one")
    second = queued("common", checkout="/worktree/two")
    other = queued("other")
    heavy = queued("common", "heavy")
    assert store.start(first, Path("fixture"))
    complete(first)
    assert not store.start(second, Path("fixture"))
    assert store.start(heavy, Path("fixture"))
    assert store.start(other, Path("fixture"))


def test_unpublished_local_jobs_do_not_block_a_ready_queue():
    queued("unpublished", published=False)
    ready = queued("ready")
    assert store.start(ready, Path("fixture"))


def test_cancelled_job_cannot_be_started_after_admission_race():
    job = queued("cancelled")
    store.finish(job, "cancelled", {}, Path("fixture-report"))
    assert not store.start(job, Path("fixture"))
    assert store.get(job)["status"] == "cancelled"


def test_missing_preferred_delivery_cannot_block_the_lane_forever():
    first = queued("a")
    following = queued("a")
    absent = queued("b")
    assert store.start(first, Path("fixture"))
    complete(first)
    assert not store.start(following, Path("fixture"))
    with store.database() as db:
        db.execute(
            "UPDATE jobs SET fair_wait_started='2000-01-01T00:00:00+00:00' WHERE id=?", (following,)
        )
    assert store.start(following, Path("fixture"))
    assert store.get(following)["fairness_bypasses"] == 1
    assert store.get(absent)["status"] == "queued"  # No implicit recovery/execution.
