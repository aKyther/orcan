"""Storage admission and cleanup use synthetic owned data only."""

import fcntl
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

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
    assert retention.prune(dry_run=True) == 1
    assert retention.prune() == 1
    assert store.get(job["id"])["details_expired"] == 1
    assert store.get(job["id"])["worktree"] == str(tree)
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


def test_completion_preserves_ignored_outputs(repo):
    from conftest import commit

    (repo / '.gitignore').write_text('site/\n.build/\nignored-data\n')
    (repo / 'check.py').write_text(
        'from pathlib import Path\n'
        'for name in ("site", ".build"):\n'
        ' Path(name).mkdir(); Path(name, "keep").write_text("preserve")\n'
        'Path("ignored-data").write_text("preserve")\n'
    )
    commit(repo)
    job = submit(repo)
    result = engine.run_job(job['id'])
    assert result['status'] == 'passed'
    tree = Path(result['summary']['retained_worktree'])
    for name in ('site/keep', '.build/keep', 'ignored-data'):
        assert (tree / name).read_text() == 'preserve'


def test_retention_timeout_does_not_block_other_jobs(repo, monkeypatch):
    import subprocess

    from conftest import commit

    from orcan_executor import worktree_cleanup

    (repo / 'check.py').write_text('from pathlib import Path\nPath("marker").write_text("dirty")\n')
    commit(repo)
    first = submit(repo)
    engine.run_job(first['id'])
    second = submit(repo)
    engine.run_job(second['id'])
    tree = Path(store.get(first['id'])['worktree'])
    with store.database() as db:
        db.execute("UPDATE jobs SET finished='2000-01-01'")
    original = worktree_cleanup.is_clean
    def inspect(path):
        if path == tree:
            raise subprocess.TimeoutExpired('git status', 30)
        return original(path)
    monkeypatch.setattr(worktree_cleanup, 'is_clean', inspect)
    other_tree = Path(store.get(second['id'])['worktree'])
    (other_tree / 'marker').write_text('snapshot')
    assert retention.prune() == 2
    assert tree.exists()
    assert store.get(first["id"])["details_expired"] == 1
    assert not other_tree.exists()


@pytest.mark.parametrize("failed_directory", ["worktree", "artifacts"])
def test_directory_setup_failure_finishes_without_report(repo, monkeypatch, failed_directory):
    job = submit(repo)
    original = Path.mkdir
    def mkdir(path, *args, **kwargs):
        target = (storage.worktree_root() / job["id"] if failed_directory == "worktree"
                  else storage.state_dir() / "jobs" / job["id"] / "1")
        if path == target:
            raise PermissionError('synthetic denied')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'mkdir', mkdir)
    result = engine.run_job(job['id'])
    assert result['status'] == 'error'
    assert result['report'] is None
    assert result['summary']['phase'] == 'setup'
    assert store.get(job['id'])['status'] == 'error'
    assert result['summary']['tests'] == 0


def test_pulse_uses_count_and_capacity_without_analytics_or_scanning(repo, monkeypatch, capsys):
    job = submit(repo)
    engine.cancel(job['id'])
    monkeypatch.setattr(store, 'board', Mock(side_effect=AssertionError('analytics not allowed')))
    monkeypatch.setattr(storage, 'size', Mock(side_effect=AssertionError('scan not allowed')))
    monkeypatch.setattr(storage, 'capacity', lambda: {'ready': False, 'filesystems': []})
    assert cli.main(['pulse']) == 0
    value = json.loads(capsys.readouterr().out)
    assert value['attention_count'] == store.attention_overview()['count'] == 1
    assert value['storage']['ready'] is False
    monkeypatch.setattr(storage, 'capacity', Mock(side_effect=OSError('unavailable')))
    assert cli.main(['pulse']) == 0
    assert json.loads(capsys.readouterr().out)['storage']['ready'] is None


def test_worktree_report_is_bounded_without_admission_budget(tmp_path, monkeypatch):
    import stat
    from types import SimpleNamespace

    root = tmp_path / "worktrees"
    root.mkdir()
    monkeypatch.setattr(storage, "worktree_root", lambda: root)
    entry = Mock()
    entry.stat.return_value = SimpleNamespace(st_mode=stat.S_IFREG, st_nlink=1, st_blocks=8)
    monkeypatch.setattr(storage.os, "scandir", lambda path: iter([entry] * 150001))
    result = storage.worktree_capacity()
    assert result["incomplete"]
    assert result["entries"] == 150000
    assert "budget_bytes" not in result


def test_streaming_accounting_deduplicates_hardlinks(tmp_path):
    root = tmp_path / "tree"
    root.mkdir()
    original = root / "original"
    original.write_bytes(b"x" * 8192)
    (root / "nested").mkdir()
    (root / "nested" / "duplicate").hardlink_to(original)
    assert storage.size(root, limit=None)["allocated_bytes"] == original.stat().st_blocks * 512


def test_incomplete_worktree_report_does_not_change_storage_readiness(monkeypatch):
    monkeypatch.setattr(storage, "capacity", lambda: {"ready": True, "filesystems": []})
    monkeypatch.setattr(storage, "size", lambda *a, **k: {
        "allocated_bytes": 100000000000, "entries": 150000, "incomplete": True,
    })
    assert storage.report()["ready"]
    assert storage.report()["worktrees"]["incomplete"]


def test_admission_never_scans_worktree_contents(repo, monkeypatch):
    monkeypatch.setattr(storage, "size", Mock(side_effect=AssertionError("no scans")))
    job = submit(repo)
    assert store.start(job["id"], storage.worktree_root() / job["id"])
    assert store.get(job["id"])["admission_reason"] is None


def test_low_space_during_execution_stops_process_and_preserves_changes(repo, monkeypatch):
    from conftest import commit

    (repo / "check.py").write_text(
        'from pathlib import Path\nimport time\n'
        'Path("marker").write_text("keep work")\ntime.sleep(30)\n'
    )
    commit(repo)
    checks = 0
    def capacity():
        nonlocal checks
        checks += 1
        ready = checks < 3
        return {"ready": ready, "filesystems": [{
            "path": "/synthetic", "ready": ready, "free_bytes": 0,
            "minimum_free_bytes": 1024**2,
        }]}
    monkeypatch.setattr(storage, "capacity", capacity)
    result = engine.run_job(submit(repo)["id"])
    assert result["status"] == "error"
    assert "Disk reserve reached" in result["summary"]["error"]
    tree = Path(store.get(result["job_id"])["worktree"])
    assert (tree / "marker").read_text() == "keep work"


@pytest.mark.parametrize("dirty", [False, True])
@pytest.mark.parametrize("locked", [False, True])
def test_low_space_maintenance_reclaims_only_clean_completed_tree_and_keeps_reports(repo, monkeypatch, dirty, locked):
    result = engine.run_job(submit(repo)["id"])
    job = store.get(result["job_id"])
    # Engine normally removes a clean completed checkout. Recreate a retained one.
    import subprocess
    tree = storage.worktree_root() / job["id"] / "retained"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "--detach", str(tree), job["sha"]],
                   check=True, capture_output=True)
    common = subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-common-dir"],
                            check=True, capture_output=True, text=True).stdout.strip()
    git_dir = str((repo / common).resolve())
    with store.database() as db:
        db.execute("UPDATE jobs SET worktree=?,git_dir=? WHERE id=?", (str(tree), git_dir, job["id"]))
    if dirty:
        (tree / "marker").write_text("keep changes")
    monkeypatch.setattr(storage, "capacity", lambda: {"ready": False})
    from contextlib import ExitStack
    with ExitStack() as stack:
        if locked:
            lock = stack.enter_context((Path(result["report"]).parent.parent / "run.lock").open("a"))
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        candidates = []
        retention.prune(dry_run=True, candidates=candidates)
        removable = not dirty and not locked
        assert bool(candidates) is removable
        if candidates:
            assert candidates[0]["reason"] == "disk_space"
            assert candidates[0]["artifacts"] is None
        retention.prune()
        assert tree.exists() is (not removable)
    assert Path(result["report"]).exists()
    assert store.get(job["id"])["details_expired"] == 0
