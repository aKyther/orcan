"""Real content fingerprints, atomic joining and durable evidence, without a broker."""

import fcntl
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
from conftest import commit
from fastapi.testclient import TestClient

from orcan_executor import (
    cli,
    engine,
    events,
    notifications,
    profiles,
    retention,
    reuse,
    store,
    web,
)


@pytest.fixture
def cached_repo(repo):
    (repo / "check.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        'assert Path("marker").read_text() == "snapshot"\n'
        'assert Path("shared.txt").read_text() == "base"\n'
        'Path(sys.argv[1]).write_text(\'<testsuite><testcase name="a"/><testcase name="b"/></testsuite>\')\n'
    )
    (repo / "shared.txt").write_text("base")
    (repo / "README.md").write_text("documentation")
    definition = {
        "steps": [{"argv": [sys.executable, "check.py", "{junit}"]}],
        "require_junit": True,
        "minimum_tests": 2,
        "reuse": {
            "ttl_seconds": 3600,
            "inputs": ["check.py", "marker", "shared.txt"],
            "tools": [[sys.executable, "--version"]],
        },
    }
    (repo / profiles.CONFIG).write_text(
        json.dumps({"version": 1, "profiles": {"quality": definition}})
    )
    commit(repo)
    return repo


def submit(repo, **kwargs):
    return engine.submit(repo, "HEAD", "verification", "quality", [], 30, **kwargs)


def passed(repo):
    job = submit(repo)
    assert engine.run_job(job["id"])["status"] == "passed"
    assert store.get(job["id"])["evidence_manifest"]
    return store.get(job["id"])


def change_profile(repo, update):
    config = json.loads((repo / profiles.CONFIG).read_text())
    update(config["profiles"]["quality"])
    (repo / profiles.CONFIG).write_text(json.dumps(config))
    commit(repo)


def test_identical_success_returns_own_receipt_without_running_tests_again(
    cached_repo, monkeypatch
):
    original = passed(cached_repo)
    monkeypatch.setattr(
        engine, "execute", lambda *args: pytest.fail("Cached result must not execute")
    )
    result = submit(cached_repo)
    assert result["id"] != original["id"]
    assert result["status"] == "passed" and result["submission_mode"] == "reused"
    assert result["attempts"] == 0 and result["worktree"] is None
    assert engine.run_job(result["id"]) is None
    assert result["summary"]["tests"] == 0
    proof = result["summary"]["verification"]
    assert proof["source_job_id"] == original["id"]
    assert proof["source_sha"] == original["sha"]
    assert proof["counts"]["tests"] == 2
    assert len(proof["inputs_sha256"]) == 64
    response = TestClient(web.app).get(f"/api/jobs/{result['id']}/report")
    assert response.json()["verification"]["kind"] == "reused"
    assert response.json()["tests"] == 0
    assert "verification" in notifications.message(result)
    assert (
        engine.git(cached_repo, "rev-parse", "refs/orcan/executor/jobs/" + result["id"])
        == result["sha"]
    )


def test_unrelated_commit_reuses_declared_inputs_and_keeps_both_shas(cached_repo):
    original = passed(cached_repo)
    (cached_repo / "README.md").write_text("changed documentation")
    commit(cached_repo)
    current = submit(cached_repo)
    assert current["status"] == "passed"
    assert current["sha"] != original["sha"]
    assert current["summary"]["verification"]["source_sha"] == original["sha"]
    assert current["input_key"] == original["input_key"]


def test_full_tree_default_invalidates_when_any_tracked_file_changes(cached_repo):
    change_profile(cached_repo, lambda d: d["reuse"].pop("inputs"))
    passed(cached_repo)
    (cached_repo / "README.md").write_text("changed documentation")
    commit(cached_repo)
    assert submit(cached_repo)["status"] == "queued"


@pytest.mark.parametrize("path", ["check.py", "marker", "shared.txt"])
def test_changed_source_or_shared_dependency_never_inherits_success(cached_repo, path):
    passed(cached_repo)
    with (cached_repo / path).open("a") as handle:
        handle.write("changed")
    commit(cached_repo)
    current = submit(cached_repo)
    assert current["status"] == "queued" and current["reuse_source"] is None


def test_profile_and_scope_changes_invalidate(cached_repo):
    passed(cached_repo)
    change_profile(cached_repo, lambda d: d.update(minimum_tests=3))
    assert submit(cached_repo)["status"] == "queued"


def test_selected_tests_are_part_of_identity(cached_repo):
    change_profile(
        cached_repo,
        lambda d: (d.update(requires_tests=True), d["steps"][0]["argv"].append("{tests}")),
    )
    one = engine.submit(cached_repo, "HEAD", "one", "quality", ["A"], 30)
    assert engine.run_job(one["id"])["status"] == "passed"
    two = engine.submit(cached_repo, "HEAD", "two", "quality", ["B"], 30)
    assert two["status"] == "queued"
    assert engine.submit(cached_repo, "HEAD", "again", "quality", ["A"], 30)["status"] == "passed"


def test_concurrent_producers_share_one_execution_and_keep_all_requests(cached_repo):
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = list(pool.map(lambda _: submit(cached_repo), range(16)))
    assert len({job["id"] for job in jobs}) == 1
    assert sum(job["submission_mode"] == "created" for job in jobs) == 1
    stats = store.board()["stats"]
    assert stats["submission_requests"] == 16 and stats["joined_submissions"] == 15
    assert (
        len(engine.git(cached_repo, "for-each-ref", "refs/orcan/executor/jobs").splitlines()) == 1
    )


def test_completed_reuse_does_not_double_count_test_or_runtime_measurements(cached_repo):
    passed(cached_repo)
    before = store.board()["stats"]
    submit(cached_repo)
    after = store.board()["stats"]
    assert after["executed_jobs"] == 1 and after["reused_verifications"] == 1
    for key in ("tests", "total_run_seconds", "log_bytes", "child_cpu_seconds"):
        assert after[key] == before[key]


def test_cli_join_does_not_publish_a_duplicate_and_each_caller_can_subscribe(
    cached_repo, monkeypatch, capsys
):
    send = Mock()
    monkeypatch.setattr(cli, "enqueue", send)
    monkeypatch.setattr(events, "publish_pending", lambda: 0)
    command = ["submit", "--repo", str(cached_repo), "--profile", "quality"]
    assert cli.main(command + ["--notify-codex-thread", str(uuid4())]) == 0
    original = json.loads(capsys.readouterr().out)
    assert cli.main(command + ["--notify-codex-thread", str(uuid4())]) == 0
    joined = json.loads(capsys.readouterr().out)
    assert original["job_id"] == joined["job_id"]
    assert joined["submission"] == "joined"
    send.assert_called_once()
    assert len(notifications.listing(original["job_id"])) == 2


def test_cached_cli_result_needs_no_broker_and_force_runs_fresh(cached_repo, monkeypatch, capsys):
    original = passed(cached_repo)
    send = Mock()
    monkeypatch.setattr(cli, "enqueue", send)
    monkeypatch.setattr(
        events, "publish_pending", Mock(side_effect=ConnectionError("fixture outage"))
    )
    command = ["submit", "--repo", str(cached_repo), "--profile", "quality", "--timeout", "30"]
    assert cli.main(command) == 0
    cached = json.loads(capsys.readouterr().out)
    assert cached["status"] == "passed" and cached["submission"] == "reused"
    assert cached["verification"]["source_job_id"] == original["id"]
    send.assert_not_called()
    assert cli.main(command + ["--force"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "queued"
    send.assert_called_once()


@pytest.mark.parametrize("damage", ["missing", "tampered", "expired", "manifest", "omitted_junit"])
def test_incomplete_or_expired_evidence_forces_fresh_work(cached_repo, damage):
    original = passed(cached_repo)
    if damage == "missing":
        shutil.rmtree(Path(original["report"]).parent / "junit")
    elif damage == "tampered":
        path = Path(original["report"])
        path.write_text(path.read_text().replace('"passed"', '"failed"'))
    else:
        with store.database() as db:
            if damage == "expired":
                db.execute(
                    "UPDATE jobs SET finished='2000-01-01T00:00:00+00:00' WHERE id=?",
                    (original["id"],),
                )
            elif damage == "manifest":
                db.execute("UPDATE jobs SET evidence_manifest='[]' WHERE id=?", (original["id"],))
            else:
                manifest = [
                    row
                    for row in json.loads(original["evidence_manifest"])
                    if row[0] == "report.json"
                ]
                db.execute(
                    "UPDATE jobs SET evidence_manifest=? WHERE id=?",
                    (json.dumps(manifest), original["id"]),
                )
    assert submit(cached_repo)["status"] == "queued"


def test_later_failure_invalidates_older_success(cached_repo, monkeypatch):
    passed(cached_repo)
    fresh = submit(cached_repo, force=True)
    monkeypatch.setattr(engine, "execute", lambda *args: 1)
    assert engine.run_job(fresh["id"])["status"] == "failed"
    assert submit(cached_repo)["status"] == "queued"


def test_shared_toolchain_or_declared_environment_change_forces_fresh_work(
    cached_repo, monkeypatch, tmp_path
):
    change_profile(
        cached_repo,
        lambda d: d["reuse"].update(environment=["CACHE_FIXTURE_MODE"]),
    )
    passed(cached_repo)
    monkeypatch.setenv("CACHE_FIXTURE_MODE", "different")
    assert submit(cached_repo)["status"] == "queued"
    monkeypatch.delenv("CACHE_FIXTURE_MODE")
    original = reuse.file_digest
    executable = Path(sys.executable).resolve()
    monkeypatch.setattr(
        reuse, "file_digest", lambda path: "f" * 64 if path == executable else original(path)
    )
    assert submit(cached_repo)["status"] == "queued"


def test_environment_changed_before_execution_is_not_sealed(cached_repo, monkeypatch):
    original = submit(cached_repo)
    monkeypatch.setenv("ORCAN_EXECUTOR_CACHE_EPOCH", "changed")
    assert engine.run_job(original["id"])["status"] == "passed"
    assert store.get(original["id"])["evidence_manifest"] is None


def test_reused_receipt_survives_pruning_original_evidence(cached_repo):
    original = passed(cached_repo)
    current = submit(cached_repo)
    with store.database() as db:
        stamp = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        db.execute("UPDATE jobs SET finished=? WHERE id=?", (stamp, original["id"]))
    assert retention.prune() == 1
    assert Path(current["report"]).is_file()
    evidence = Path(current["report"]).parent / "evidence/report.json"
    assert json.loads(evidence.read_text())["sha"] == original["sha"]
    assert submit(cached_repo)["status"] == "queued"  # A reuse never renews original validity.


def test_held_source_lock_does_not_deadlock_retention_or_reuse(cached_repo):
    original = passed(cached_repo)
    lockfile = store.state_dir() / "jobs" / original["id"] / "run.lock"
    with lockfile.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert submit(cached_repo)["status"] == "queued"


@pytest.mark.parametrize(
    "path,pattern,expected",
    [
        ("src/a.py", "src/**/*.py", True),
        ("src/x/a.py", "src/**/*.py", True),
        ("src/x/a.py", "src/*.py", False),
        ("tests/A.java", "tests/**/*.java", True),
        ("src/a.py", "./src/**", True),
        ("src-other/a.py", "src/**", False),
        ("pyproject.toml", "pyproject.toml", True),
    ],
)
def test_generic_input_globs_cover_python_and_java_without_crossing_segments(
    path, pattern, expected
):
    assert reuse.matches(path, pattern) is expected


@pytest.mark.parametrize(
    "update",
    [
        {"ttl_seconds": 0},
        {"inputs": []},
        {"inputs": ["../outside"]},
        {"environment": ["API_TOKEN"]},
        {"tools": [["python", "arbitrary.py"]]},
    ],
)
def test_invalid_reuse_contract_is_rejected(cached_repo, update):
    config = json.loads((cached_repo / profiles.CONFIG).read_text())
    config["profiles"]["quality"]["reuse"].update(update)
    with pytest.raises(ValueError):
        profiles.load(json.dumps(config))


def test_external_profiles_remain_fresh_by_default(repo):
    original = engine.submit(repo, "HEAD", "original", "quality", [], 30)
    assert engine.run_job(original["id"])["status"] == "passed"
    current = engine.submit(repo, "HEAD", "new", "quality", [], 30, reuse=True)
    assert current["status"] == "queued" and current["reuse_source"] is None


@pytest.mark.parametrize("change", ["rename", "delete", "mode"])
def test_input_path_deletion_and_executable_mode_are_part_of_identity(cached_repo, change):
    original = passed(cached_repo)
    if change == "rename":
        (cached_repo / "shared.txt").rename(cached_repo / "renamed.txt")
    elif change == "delete":
        (cached_repo / "shared.txt").unlink()
    else:
        (cached_repo / "check.py").chmod(0o755)
    commit(cached_repo)
    current = submit(cached_repo)
    assert current["status"] == "queued"
    assert current["verification_key"] != original["verification_key"]


def test_missing_version_probe_disables_reuse_without_failing_the_operation(cached_repo):
    change_profile(
        cached_repo,
        lambda d: d["reuse"].update(tools=[["/nonexistent/orcan-version-fixture", "--version"]]),
    )
    job = submit(cached_repo)
    assert job["reuse_note"] and job["verification_key"] is None
    assert engine.run_job(job["id"])["status"] == "passed"
    assert submit(cached_repo)["status"] == "queued"


def test_symlink_input_is_not_assumed_to_have_stable_external_content(cached_repo):
    (cached_repo / "link").symlink_to("marker")
    change_profile(cached_repo, lambda d: d["reuse"]["inputs"].append("link"))
    job = submit(cached_repo)
    assert job["status"] == "queued" and job["verification_key"] is None


def test_cache_hit_can_return_when_execution_queue_is_full(cached_repo, monkeypatch):
    original = passed(cached_repo)
    monkeypatch.setenv("ORCAN_EXECUTOR_MAX_PENDING", "1")
    fresh = engine.submit(cached_repo, "HEAD", "different timeout", "quality", [], 31, force=True)
    assert fresh["status"] == "queued"
    cached = submit(cached_repo)
    assert cached["reuse_source"] == original["id"] and cached["status"] == "passed"


def test_different_repositories_never_share_a_verdict(cached_repo, tmp_path):
    original = passed(cached_repo)
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(cached_repo), str(other)], check=True)
    current = submit(other)
    assert current["sha"] == original["sha"]
    assert current["status"] == "queued" and current["reuse_source"] is None


def test_producer_and_separate_worker_process_agree_on_identity(cached_repo):
    original = submit(cached_repo)
    worker = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from orcan_executor import engine; engine.run_job(sys.argv[1])",
            original["id"],
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert worker.returncode == 0, worker.stderr[-1000:]
    assert store.get(original["id"])["evidence_manifest"]
    producer = subprocess.run(
        [
            sys.executable,
            "-m",
            "orcan_executor.cli",
            "submit",
            "--repo",
            str(cached_repo),
            "--profile",
            "quality",
            "--timeout",
            "30",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert producer.returncode == 0, producer.stdout[-1000:]
    current = json.loads(producer.stdout)
    assert current["submission"] == "reused"
    assert current["verification"]["source_job_id"] == original["id"]


def test_loaded_code_identity_does_not_depend_on_serialization_history():
    prefix = "from orcan_executor import reuse; "
    cold = subprocess.check_output(
        [sys.executable, "-c", prefix + "print(reuse.loaded_runner_key())"], text=True
    )
    warm = subprocess.check_output(
        [
            sys.executable,
            "-c",
            prefix
            + "import marshal; [marshal.dumps(v.__code__) for v in vars(reuse).values() if hasattr(v, '__code__')]; print(reuse.loaded_runner_key())",
        ],
        text=True,
    )
    assert cold == warm


def test_profiles_exposes_reuse_contract_without_environment_values(cached_repo, capsys):
    assert cli.main(["profiles", "--repo", str(cached_repo)]) == 0
    procedure = json.loads(capsys.readouterr().out)["procedures"][0]
    assert procedure["reuse"] == {"enabled": True, "ttl_seconds": 3600, "inputs": "declared"}


def test_new_container_generation_requires_fresh_verification(cached_repo, monkeypatch):
    passed(cached_repo)
    monkeypatch.setattr(reuse, "runtime_generation", lambda: ["new container", "same host"])
    assert submit(cached_repo)["status"] == "queued"


def test_submission_history_is_bounded_without_removing_active_execution(cached_repo):
    job = submit(cached_repo)
    with store.database() as db:
        db.executemany(
            "INSERT INTO submissions(id,job_id,created,mode,sha,task) VALUES(?,?,?,?,?,?)",
            [
                (str(i), job["id"], store.now(), "joined", job["sha"], "fixture")
                for i in range(10001)
            ],
        )
    assert retention.prune() == 0
    with store.database() as db:
        assert db.execute("SELECT COUNT(*) FROM submissions").fetchone()[0] == 10000
    assert store.get(job["id"])["status"] == "queued"


def test_checkout_failure_still_returns_terminal_error_for_a_cacheable_operation(
    cached_repo, monkeypatch
):
    job = submit(cached_repo)
    monkeypatch.setattr(
        engine.subprocess, "run", Mock(side_effect=OSError("fixture checkout unavailable"))
    )
    result = engine.run_job(job["id"])
    assert result["status"] == "error"
    assert "fixture checkout unavailable" in result["summary"]["error"]
    assert store.get(job["id"])["status"] == "error"
    assert store.get(job["id"])["evidence_manifest"] is None
