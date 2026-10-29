import json
import os

import pytest

from orcan_executor import engine, snapshots, store


def project(tmp_path):
    root = tmp_path / "plain"
    (root / ".orcan").mkdir(parents=True)
    (root / ".orcan/checks.json").write_text(
        json.dumps(
            {"version": 1, "profiles": {"check": {"steps": [{"argv": ["python3", "check.py"]}]}}}
        )
    )
    (root / "check.py").write_text(
        'from pathlib import Path\nassert Path("input.txt").read_text() == "original"\n'
    )
    (root / "input.txt").write_text("original")
    return root


def test_plain_directory_snapshot_is_pinned_isolated_and_reusable(tmp_path):
    source = project(tmp_path)
    (source / ".env").write_text("NEVER_COPY")
    with snapshots.snapshot(source, ["check.py", "input.txt"]) as repository:
        job = engine.submit(repository, "HEAD", "plain", "check", [], 30)
        first_sha = job["sha"]
        first_repository = repository
        assert not (repository / ".env").exists()
    (source / "input.txt").write_text("editing")
    assert engine.run_job(job["id"])["status"] == "passed"
    assert not (source / ".git").exists()
    assert (source / "input.txt").read_text() == "editing"
    (source / "input.txt").write_text("original")
    with snapshots.snapshot(source, ["input.txt", "check.py"]) as repository:
        assert repository == first_repository
        assert engine.git(repository, "rev-parse", "HEAD") == first_sha


@pytest.mark.parametrize("name", [".env", ".env.local", "runtime.conf", "../escape", ".git/config"])
def test_sensitive_and_outside_paths_are_rejected_before_read(tmp_path, name):
    source = project(tmp_path)
    with pytest.raises(ValueError):
        with snapshots.snapshot(source, [name]):
            pytest.fail("Snapshot should be rejected")


def test_symlinks_and_oversized_files_are_rejected(tmp_path):
    source = project(tmp_path)
    (source / "linked.py").symlink_to(source / "check.py")
    with pytest.raises(ValueError, match="symlink"):
        with snapshots.snapshot(source, ["linked.py"]):
            pass
    with (source / "large").open("wb") as stream:
        stream.truncate(snapshots.MAX_FILE_BYTES + 1)
    with pytest.raises(ValueError, match="8 MiB"):
        with snapshots.snapshot(source, ["large"]):
            pass


def test_cache_ttl_preserves_referenced_snapshots_then_removes_unreferenced(tmp_path):
    source = project(tmp_path)
    with snapshots.snapshot(source, ["check.py", "input.txt"]) as repository:
        job = engine.submit(repository, "HEAD", "plain", "check", [], 30)
        marker = repository / ".git/orcan-directory-snapshot"
    os.utime(marker, (1, 1))
    assert snapshots.prune_snapshots() == 0
    assert repository.exists()
    with store.database() as db:
        db.execute("DELETE FROM jobs WHERE id=?", (job["id"],))
    assert snapshots.prune_snapshots() == 1
    assert not repository.exists()


def test_explicit_file_selection_is_required(tmp_path):
    source = project(tmp_path)
    with pytest.raises(ValueError, match="explicit"):
        with snapshots.snapshot(source, []):
            pass
