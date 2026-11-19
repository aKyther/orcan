"""Disk budgets bound output and expire artifacts without destroying checkouts."""

import json
from pathlib import Path

import pytest
from conftest import commit

from orcan_executor import engine, profiles, retention, settings, storage, store, worktree_cleanup


def submit(repo):
    return engine.submit(repo, "HEAD", "limits", "quality", [], 30)


def test_noisy_command_stops_at_limit_and_cannot_pass(repo, monkeypatch):
    monkeypatch.setenv("ORCAN_EXECUTOR_LOG_LIMIT_MB", "1")
    (repo / "check.py").write_text('import os\nwhile True: os.write(1,b"x"*65536)\n')
    commit(repo)
    result = engine.run_job(submit(repo)["id"])
    assert result["status"] == "error"
    assert "log_limit_mb" in result["summary"]["error"]
    report = Path(result["report"])
    assert report.with_name("output.log").stat().st_size < 1024**2 + 4096
    assert 1024**2 - 4096 <= (report.parent / "steps/step-001.log").stat().st_size <= 1024**2


def test_silent_command_timeout_is_preserved(repo):
    (repo / "check.py").write_text("import time\ntime.sleep(20)\n")
    commit(repo)
    job = engine.submit(repo, "HEAD", "limits", "quality", [], 1)
    assert engine.run_job(job["id"])["status"] == "timed_out"


def test_oversized_artifact_cannot_pass_and_is_not_copied(repo, monkeypatch):
    monkeypatch.setenv("ORCAN_EXECUTOR_ARTIFACT_LIMIT_MB", "1")
    cfg = json.loads((repo / profiles.CONFIG).read_text())
    cfg["profiles"]["quality"]["artifacts"] = ["large.dat"]
    (repo / profiles.CONFIG).write_text(json.dumps(cfg))
    (repo / "check.py").write_text(
        'from pathlib import Path\nPath("large.dat").write_bytes(b"a"*2*1024**2)\n'
    )
    commit(repo)
    result = engine.run_job(submit(repo)["id"])
    assert result["status"] == "error"
    assert "artifact_limit_mb" in result["summary"]["error"]
    assert not (Path(result["report"]).parent / "artifacts/large.dat").exists()


def test_budget_expires_oldest_completed_before_ttl_and_preserves_dirty_tree(repo, monkeypatch):
    monkeypatch.setenv("ORCAN_EXECUTOR_DETAIL_BUDGET_MB", "1")
    (repo / "check.py").write_text('from pathlib import Path\nPath("marker").write_text("keep")\n')
    commit(repo)
    first = submit(repo)
    result = engine.run_job(first["id"])
    tree = Path(store.get(first["id"])["worktree"])
    report = Path(result["report"])
    (report.parent / "old-output").write_bytes(b"x" * 2 * 1024**2)
    queued = submit(repo)
    assert retention.prune(dry_run=True) == 1
    assert report.exists()
    assert retention.prune() == 1
    assert not report.exists()
    assert (tree / "marker").read_text() == "keep"
    assert store.get(first["id"])["details_expired"] == 1
    assert store.get(first["id"])["worktree"] == str(tree)
    assert (settings.state_dir() / "jobs" / first["id"] / "run.lock").exists()
    assert store.get(queued["id"])["status"] == "queued"
    # Preserved trees remain eligible for conservative removal after restoration.
    (tree / "marker").write_text("snapshot")
    with store.database() as db:
        db.execute("UPDATE jobs SET finished='2000-01-01' WHERE id=?", (first["id"],))
    assert retention.prune() == 1
    assert not tree.exists()


def test_worktree_budget_pauses_new_work(repo, monkeypatch):
    monkeypatch.setenv("ORCAN_EXECUTOR_WORKTREE_BUDGET_MB", "1")
    tree = settings.worktree_root()
    tree.mkdir(parents=True)
    (tree / "reserved").write_bytes(b"x" * 2 * 1024**2)
    job = submit(repo)
    assert engine.run_job(job["id"]) is None
    assert store.get(job["id"])["attempts"] == 0
    assert (tree / "reserved").exists()


def test_bounded_copy_preserves_existing_destination(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.write_bytes(b"content")
    target.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        storage.bounded_copy(source, target, 100)
    assert target.read_bytes() == b"keep"


def test_archived_report_cleanup_is_explicit_and_preserves_unarchived_or_tracked_files(repo):
    archive = repo.parent / "archive"
    archive.mkdir()
    (archive / "TEST-0.xml").write_text("matching report")
    (repo / "tracked.xml").write_text("matching report")
    commit(repo)
    (repo / "generated.xml").write_text("matching report")
    (repo / "not-archived.xml").write_text("other report")
    assert worktree_cleanup.archived_reports(repo, archive, {"junit": ["*.xml"]}) == 1
    assert not (repo / "generated.xml").exists()
    assert (repo / "tracked.xml").exists()
    assert (repo / "not-archived.xml").exists()


def test_opt_in_cleanup_allows_worktree_completion_without_retaining_duplicate_junit(repo):
    cfg = json.loads((repo / profiles.CONFIG).read_text())
    cfg["profiles"]["quality"].update(
        junit=["out/results.xml"], require_junit=True, cleanup_archived_reports=True
    )
    (repo / profiles.CONFIG).write_text(json.dumps(cfg))
    (repo / "check.py").write_text(
        'from pathlib import Path\nPath("out").mkdir()\nPath("out/results.xml").write_text(\'<testsuite><testcase name="ok"/></testsuite>\')\n'
    )
    commit(repo)
    job = submit(repo)
    result = engine.run_job(job["id"])
    assert result["status"] == "passed"
    assert result["summary"]["passed"] == 1
    assert not Path(store.get(job["id"])["worktree"]).exists()
    assert (Path(result["report"]).parent / "junit/TEST-0.xml").exists()


def test_incomplete_worktree_accounting_pauses_admission(repo, monkeypatch):
    monkeypatch.setattr(
        storage,
        "size",
        lambda *args, **kwargs: {"allocated_bytes": 0, "entries": 1, "incomplete": True},
    )
    job = submit(repo)
    assert engine.run_job(job["id"]) is None
    assert store.get(job["id"])["attempts"] == 0


def test_budget_preserves_locked_completed_artifacts(repo, monkeypatch):
    import fcntl

    monkeypatch.setenv("ORCAN_EXECUTOR_DETAIL_BUDGET_MB", "1")
    result = engine.run_job(submit(repo)["id"])
    report = Path(result["report"])
    (report.parent / "large").write_bytes(b"x" * 2 * 1024**2)
    with (report.parent.parent / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert retention.prune() == 0
        assert report.exists()


def test_growing_artifact_removes_partial_destination(tmp_path, monkeypatch):
    from unittest.mock import Mock

    source, target = tmp_path / "growing", tmp_path / "copy"
    source.write_bytes(b"x" * 100)
    monkeypatch.setattr(storage.os, "fstat", lambda fd: Mock(st_size=0))
    with pytest.raises(ValueError, match="artifact_limit_mb"):
        storage.bounded_copy(source, target, 10)
    assert not target.exists()
    assert source.stat().st_size == 100


def test_archived_report_preview_and_symlink_preservation(repo, tmp_path):
    archive = tmp_path / "evidence"
    archive.mkdir()
    (archive / "TEST.xml").write_text("report")
    report = repo / "generated.xml"
    report.write_text("report")
    definition = {"junit": ["*.xml"]}
    assert worktree_cleanup.archived_reports(repo, archive, definition, dry_run=True) == 1
    assert report.exists()
    link = tmp_path / "linked-evidence"
    link.symlink_to(archive, target_is_directory=True)
    assert worktree_cleanup.archived_reports(repo, link, definition) == 0
    assert report.exists()


def test_per_job_log_budget_is_shared_by_steps(repo, monkeypatch):
    monkeypatch.setenv("ORCAN_EXECUTOR_LOG_LIMIT_MB", "1")
    (repo / "check.py").write_text('import os\nos.write(1,b"x"*700000)\n')
    cfg = json.loads((repo / profiles.CONFIG).read_text())
    cfg["profiles"]["quality"]["steps"] = [
        {"argv": ["python3", "check.py"]},
        {"argv": ["python3", "check.py"]},
    ]
    (repo / profiles.CONFIG).write_text(json.dumps(cfg))
    commit(repo)
    result = engine.run_job(submit(repo)["id"])
    assert result["status"] == "error"
    report = Path(result["report"])
    assert report.with_name("output.log").stat().st_size == 1024**2


@pytest.mark.parametrize("extra", [None, "untracked", "ignored", "tracked", "link"])
def test_reviewed_ignored_outputs_only_allow_disposable_directories(repo, extra):
    (repo / ".gitignore").write_text("build/\nprivate/\n")
    cfg = json.loads((repo / profiles.CONFIG).read_text())
    cfg["profiles"]["quality"]["cleanup_ignored"] = ["build"]
    (repo / profiles.CONFIG).write_text(json.dumps(cfg))
    script = 'from pathlib import Path\nPath("build").mkdir()\nPath("build/result").write_text("generated")\n'
    if extra == "untracked":
        script += 'Path("notes").write_text("keep")\n'
    elif extra == "ignored":
        script += 'Path("private").mkdir()\nPath("private/notes").write_text("keep")\n'
    elif extra == "tracked":
        script += 'Path("marker").write_text("keep")\n'
    elif extra == "link":
        script += 'import shutil\nshutil.rmtree("build")\nPath("build").symlink_to("private", target_is_directory=True)\n'
    (repo / "check.py").write_text(script)
    commit(repo)
    job = submit(repo)
    result = engine.run_job(job["id"])
    assert result["status"] == "passed"
    tree = Path(store.get(job["id"])["worktree"])
    assert tree.exists() == (extra is not None)
    if extra is not None:
        with store.database() as db:
            db.execute("UPDATE jobs SET finished='2000-01-01' WHERE id=?", (job["id"],))
        retention.prune()
        assert tree.exists()


def test_retention_removes_reviewed_outputs_after_tracked_changes_are_restored(repo):
    (repo / ".gitignore").write_text("build/\n")
    cfg = json.loads((repo / profiles.CONFIG).read_text())
    cfg["profiles"]["quality"]["cleanup_ignored"] = ["build"]
    (repo / profiles.CONFIG).write_text(json.dumps(cfg))
    (repo / "check.py").write_text(
        'from pathlib import Path\nPath("build").mkdir()\n'
        'Path("build/output").write_text("generated")\nPath("marker").write_text("dirty")\n'
    )
    commit(repo)
    job = submit(repo)
    engine.run_job(job["id"])
    tree = Path(store.get(job["id"])["worktree"])
    (tree / "marker").write_text("snapshot")
    with store.database() as db:
        db.execute("UPDATE jobs SET finished='2000-01-01' WHERE id=?", (job["id"],))
    assert retention.prune(dry_run=True) == 1
    assert tree.exists()
    assert retention.prune() == 1
    assert not tree.exists()


@pytest.mark.parametrize("output", [".", "../outside", "/tmp", ".git", "build/*", "build/../other"])
def test_cleanup_directories_must_be_literal_and_inside_snapshot(output):
    cfg = {
        "version": 1,
        "profiles": {"quality": {"steps": [{"argv": ["true"]}], "cleanup_ignored": [output]}},
    }
    with pytest.raises(ValueError):
        profiles.load(json.dumps(cfg))


@pytest.mark.parametrize("kind", ["python", "java", "scala"])
def test_generated_profiles_declare_reviewable_output_paths(repo, kind):
    definitions = profiles.load(json.dumps(profiles.template(kind, repo)))
    assert definitions["full"]["cleanup_ignored"]
    assert definitions["docs"]["cleanup_ignored"]


@pytest.mark.parametrize(
    "output,marker",
    [
        (".venv", ".venv/pyvenv.cfg"),
        (".venv-docs", ".venv-docs/pyvenv.cfg"),
        ("pkg/__pycache__", None),
        ("src-tauri/target", "src-tauri/Cargo.toml"),
        ("target", "target/.rustc_info.json"),
        ("java/build", "java/build.gradle"),
        ("java/.build", "java/build.gradle.kts"),
        ("java/.gradle", "java/settings.gradle"),
        ("node_modules", "package.json"),
        ("site", "mkdocs.yml"),
        ("target", "pom.xml"),
    ],
)
def test_tool_outputs_do_not_retain_completed_executor_worktree(repo, output, marker):
    (repo / ".gitignore").write_text(output + "/\n")
    if marker and not marker.startswith(output + "/"):
        path = repo / marker
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("tool configuration")
    script = (
        "from pathlib import Path\n"
        f"output = Path({output!r})\noutput.mkdir(parents=True)\n"
        '(output / "generated").write_text("disposable")\n'
    )
    if marker and marker.startswith(output + "/"):
        script += f'Path({marker!r}).write_text("tool marker")\n'
    (repo / "check.py").write_text(script)
    commit(repo)
    job = submit(repo)
    result = engine.run_job(job["id"])
    assert result["status"] == "passed"
    assert not Path(store.get(job["id"])["worktree"]).exists()


@pytest.mark.parametrize("output", [".venv", "target", "build", "site", "node_modules"])
def test_unidentified_ignored_directories_are_preserved(repo, output):
    (repo / ".gitignore").write_text(output + "/\n")
    commit(repo)
    path = repo / output
    path.mkdir()
    (path / "keep").write_text("not identified as a tool output")
    assert worktree_cleanup.generated_outputs(repo) == []
    assert not worktree_cleanup.removable(repo, {})
    assert (path / "keep").exists()


def test_recognized_outputs_do_not_hide_user_changes_or_symlinks(repo):
    (repo / ".gitignore").write_text(".venv/\n")
    commit(repo)
    path = repo / ".venv"
    path.mkdir()
    (path / "pyvenv.cfg").touch()
    assert worktree_cleanup.removable(repo, {})
    (repo / "marker").write_text("user changes")
    assert not worktree_cleanup.removable(repo, {})
    (repo / "marker").write_text("snapshot")
    (repo / "notes").write_text("untracked user notes")
    assert not worktree_cleanup.removable(repo, {})
    (repo / "notes").unlink()
    (path / "pyvenv.cfg").unlink()
    path.rmdir()
    path.symlink_to(repo.parent, target_is_directory=True)
    assert worktree_cleanup.generated_outputs(repo) == []
    assert not worktree_cleanup.removable(repo, {})
