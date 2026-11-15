"""Storage admission and cleanup use synthetic owned data only."""

import fcntl
import json
from pathlib import Path
from unittest.mock import Mock

from orcan_executor import cli, engine, retention, storage, store


def submit(repo):
    return engine.submit(repo, "HEAD", "storage", "quality", [], 30)


def test_low_space_keeps_job_queued_without_attempt_or_checkout(repo, monkeypatch):
    job = submit(repo)
    monkeypatch.setattr(storage, "capacity", lambda: {"ready": False})
    assert engine.run_job(job["id"]) is None
    pending = store.get(job["id"])
    assert pending["status"] == "queued"
    assert pending["admission_reason"] == "disk_space"
    assert store.attention_overview()["jobs"][0]["admission_reason"] == "disk_space"
    assert pending["attempts"] == 0
    assert pending["started"] is None
    assert not (storage.worktree_root() / job["id"]).exists()
    monkeypatch.setattr(storage, "capacity", lambda: {"ready": True})
    assert engine.run_job(job["id"])["status"] == "passed"


def test_capacity_checks_both_filesystems(tmp_path, monkeypatch):
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setattr(storage, "worktree_root", lambda: other)

    def usage(path):
        return Mock(free=0 if path == other else 2 * 1024**3, total=3 * 1024**3)

    monkeypatch.setattr(storage.shutil, "disk_usage", usage)
    assert not storage.capacity()["ready"]


def test_accounting_does_not_follow_links_and_is_bounded(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private").write_bytes(b"x" * 8192)
    owned = tmp_path / "owned"
    owned.mkdir()
    (owned / "link").symlink_to(outside, target_is_directory=True)
    assert storage.size(owned)["allocated_bytes"] == 0
    assert storage.size(owned, limit=1)["incomplete"]


def test_cleanup_preview_preserves_artifacts_and_refs(repo, capsys):
    job = submit(repo)
    result = engine.run_job(job["id"])
    report = Path(result["report"])
    with store.database() as db:
        db.execute("UPDATE jobs SET finished='2000-01-01' WHERE id=?", (job["id"],))
    assert cli.main(["storage", "clean"]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["dry_run"] and preview["expired_jobs"] == 1
    assert preview["candidates"][0]["job_id"] == job["id"]
    assert report.exists()
    assert store.get(job["id"])["details_expired"] == 0
    assert engine.git(repo, "rev-parse", "refs/orcan/executor/jobs/" + job["id"])
    assert retention.prune() == 1
    assert not report.exists()


def test_cleanup_skips_locked_job(repo):
    job = submit(repo)
    engine.run_job(job["id"])
    with store.database() as db:
        db.execute("UPDATE jobs SET finished='2000-01-01' WHERE id=?", (job["id"],))
    with (storage.state_dir() / "jobs" / job["id"] / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert retention.prune(dry_run=True) == 0
        assert retention.prune() == 0


def test_cleanup_preserves_ignored_user_files(repo):
    (repo / ".gitignore").write_text("ignored-data\n")
    (repo / "check.py").write_text('from pathlib import Path\nPath("marker").write_text("dirty")\n')
    from conftest import commit

    commit(repo)
    job = submit(repo)
    result = engine.run_job(job["id"])
    tree = Path(result["summary"]["retained_worktree"])
    (tree / "marker").write_text("snapshot")
    (tree / "ignored-data").write_text("preserve")
    with store.database() as db:
        db.execute("UPDATE jobs SET finished='2000-01-01' WHERE id=?", (job["id"],))
    assert retention.prune(dry_run=True) == 0
    assert retention.prune() == 0
    assert (tree / "ignored-data").read_text() == "preserve"


def test_unreadable_disk_blocks_admission(repo, monkeypatch):
    job = submit(repo)
    def unreadable():
        raise OSError("unavailable filesystem")
    monkeypatch.setattr(storage, "capacity", unreadable)
    assert engine.run_job(job["id"]) is None
    assert store.get(job["id"])["admission_reason"] == "disk_space"


def test_invalid_apply_report_is_rejected(capsys):
    assert cli.main(["storage", "--apply"]) == 1
    assert "requires storage clean" in capsys.readouterr().out


def test_unused_snapshot_preview_then_apply(repo, monkeypatch):
    import os

    from orcan_executor import settings, snapshots

    with snapshots.snapshot(repo, ["marker"]) as directory:
        saved = directory
    marker = saved / ".git/orcan-directory-snapshot"
    os.utime(marker, (1, 1))
    monkeypatch.setattr(settings, "retention_seconds", lambda: 60)
    assert snapshots.prune_snapshots(dry_run=True) == 1
    assert saved.exists()
    assert snapshots.prune_snapshots() == 1
    assert not saved.exists()
