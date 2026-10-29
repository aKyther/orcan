import json
from pathlib import Path

import pytest
from conftest import commit

from orcan_executor import cli, engine, profiles, retention, store


def submit(repo, **kwargs):
    return engine.submit(
        repo,
        "HEAD",
        "task",
        kwargs.get("profile", "selected"),
        kwargs.get("tests", ["Test"]),
        kwargs.get("timeout", 30),
    )


def test_snapshot_isolation_cleanup_and_small_success(repo):
    job = submit(repo)
    (repo / "marker").write_text("agent editing")
    result = engine.run_job(job["id"])
    assert result["status"] == "passed"
    assert "noise" not in json.dumps(result)
    assert len(json.dumps(result)) < 1500
    assert (repo / "marker").read_text() == "agent editing"
    record = store.get(job["id"])
    assert not Path(record["worktree"]).exists()
    assert Path(record["report"]).with_name("output.log").stat().st_size > 100000
    assert engine.run_job(job["id"]) is None


def test_removed_agent_tree_and_branch_keep_pinned_snapshot(repo, tmp_path):
    agent = tmp_path / "agent"
    engine.git(repo, "worktree", "add", "-b", "agent-task", str(agent))
    job = submit(agent)
    engine.git(repo, "worktree", "remove", str(agent))
    engine.git(repo, "branch", "-D", "agent-task")
    assert engine.run_job(job["id"])["status"] == "passed"


@pytest.mark.parametrize(
    "profile,tests", [("selected", []), ("quality", ["Test"]), ("unknown", [])]
)
def test_scope_rejected_before_pinning(repo, profile, tests):
    with pytest.raises(ValueError):
        submit(repo, profile=profile, tests=tests)
    assert store.listing() == []
    assert engine.git(repo, "for-each-ref", "refs/orcan/executor/jobs") == ""


def test_configuration_comes_from_commit_not_dirty_files(repo):
    (repo / profiles.CONFIG).write_text("{}")
    assert engine.run_job(submit(repo)["id"])["status"] == "passed"


def test_timeout(repo):
    (repo / "check.py").write_text("import time\ntime.sleep(30)\n")
    commit(repo)
    job = submit(repo, timeout=1)
    assert engine.run_job(job["id"])["status"] == "timed_out"
    assert not Path(store.get(job["id"])["worktree"]).exists()


def test_junit_failure_and_chunked_log_read(repo, capsys):
    (repo / "check.py").write_text(
        'from pathlib import Path\nPath("junit.xml").write_text(\'<testsuite><testcase name="bad"><failure message="broken">\' + "trace" * 10000 + \'</failure></testcase></testsuite>\')\nprint("error" * 10000)\n'
    )
    config = json.loads((repo / profiles.CONFIG).read_text())
    config["profiles"]["selected"]["junit"] = ["junit.xml"]
    (repo / profiles.CONFIG).write_text(json.dumps(config))
    # Generated report is ignored so a clean executor tree can be safely removed.
    (repo / ".gitignore").write_text("junit.xml\n")
    commit(repo)
    job = submit(repo)
    result = engine.run_job(job["id"])
    assert result["status"] == "failed"
    assert result["summary"]["failed"] == 1
    assert "trace" not in json.dumps(result)
    assert cli.main(["logs", job["id"], "--limit", "123"]) == 0
    chunk = json.loads(capsys.readouterr().out)
    assert len(chunk["text"]) == 123 and chunk["next_offset"] == 123 and chunk["more"]
    assert cli.main(["logs", job["id"], "--limit", "16001"]) == 1


def test_dirty_executor_tree_is_preserved_after_ttl(repo):
    (repo / "check.py").write_text('from pathlib import Path\nPath("marker").write_text("dirty")\n')
    commit(repo)
    job = submit(repo)
    result = engine.run_job(job["id"])
    retained = Path(result["summary"]["retained_worktree"])
    with store.database() as db:
        db.execute("UPDATE jobs SET finished='2000-01-01' WHERE id=?", (job["id"],))
    assert retention.prune() == 0
    assert retained.exists()
    # Only restore our synthetic fixture change, never force cleanup.
    (retained / "marker").write_text("snapshot")
    assert retention.prune() == 1
    assert not retained.exists()


def test_ttl_removes_completed_artifacts_ref_rows_but_preserves_queued(repo):
    finished = submit(repo)
    queued = submit(repo)
    engine.run_job(finished["id"])
    with store.database() as db:
        db.execute("UPDATE jobs SET finished='2000-01-01' WHERE id=?", (finished["id"],))
    assert retention.prune() == 1
    with pytest.raises(ValueError):
        store.get(finished["id"])
    assert store.get(queued["id"])["status"] == "queued"
    assert (
        engine.git(repo, "rev-parse", "refs/orcan/executor/jobs/" + queued["id"]) == queued["sha"]
    )


@pytest.mark.parametrize("kind", ["python", "java", "scala", "custom"])
def test_templates_and_expansion(kind, tmp_path):
    config = profiles.template(kind, tmp_path)
    definitions = profiles.load(json.dumps(config))
    (tmp_path / ".orcan").mkdir()
    (tmp_path / profiles.CONFIG).write_text(json.dumps(config))
    name = "selected" if "selected" in definitions else "quality"
    steps = profiles.commands(
        tmp_path, {"profile": name, "selectors": ["Suite"], "artifact_dir": str(tmp_path)}
    )
    assert steps
    assert not any("{" in arg for argv, cwd in steps for arg in argv)


def test_sbt_injection_and_escaping_cwd_rejected(tmp_path):
    (tmp_path / ".orcan").mkdir()
    (tmp_path / profiles.CONFIG).write_text(json.dumps(profiles.template("scala", tmp_path)))
    with pytest.raises(ValueError):
        profiles.commands(
            tmp_path,
            {"profile": "selected", "selectors": ["Suite;compile"], "artifact_dir": str(tmp_path)},
        )
    with pytest.raises(ValueError):
        profiles.relative("../outside")


def test_disabled_submit_does_not_queue(repo, monkeypatch, capsys):
    monkeypatch.setenv("ORCAN_REDIS_ENABLED", "0")
    assert cli.main(["submit", "--repo", str(repo), "--test", "Test"]) == 1
    assert store.listing() == []
    assert "disabled" in capsys.readouterr().out


def test_metrics_count_exact_result_and_global_reduction(repo):
    from orcan_executor.metrics import model_result, wire

    event = engine.run_job(submit(repo)["id"])
    metrics = event["summary"]["metrics"]
    assert metrics["result_bytes"] == len(wire(model_result(event)).encode("utf-8")) + 1
    assert metrics["log_bytes"] > 100000
    assert metrics["reduction_bytes"] == metrics["log_bytes"] - metrics["result_bytes"]
    assert metrics["reduction_percent"] > 99
    assert metrics["executor_cpu_seconds"] >= 0
    board = store.board()
    assert board["stats"]["completed_jobs"] == 1
    assert board["stats"]["reduction_bytes"] == metrics["reduction_bytes"]
    assert board["jobs"][0]["progress"]["index"] == 1
    assert board["jobs"][0]["progress"]["total"] == 1


def test_quiet_tasks_can_have_negative_savings(repo):
    (repo / "check.py").write_text("pass\n")
    commit(repo)
    event = engine.run_job(submit(repo)["id"])
    assert event["summary"]["metrics"]["reduction_bytes"] < 0
    assert event["summary"]["metrics"]["estimated_tokens_avoided"] == 0


def test_long_xml_artifact_can_be_read_in_chunks(repo, capsys):
    job = submit(repo)
    engine.run_job(job["id"])
    assert cli.main(["artifacts", job["id"]]) == 0
    assert "report.json" in json.loads(capsys.readouterr().out)["artifacts"]
    assert cli.main(["logs", job["id"], "--artifact", "report.json", "--limit", "80"]) == 0
    assert json.loads(capsys.readouterr().out)["next_offset"] == 80
    assert cli.main(["logs", job["id"], "--artifact", "../outside"]) == 1


def test_pytest_parametrized_node_id_with_comma_is_preserved(repo):
    node = "tests/test_feature.py::test_case[left,right]"
    assert submit(repo, tests=[node])["selectors"] == [node]


def test_named_instances_have_separate_state_and_queue(monkeypatch):
    from orcan_executor import settings

    monkeypatch.delenv("ORCAN_EXECUTOR_STATE_DIR")
    monkeypatch.delenv("ORCAN_EXECUTOR_QUEUE")
    monkeypatch.setenv("ORCAN_NAMED_INSTANCE", "alpha")
    first = (settings.state_dir(), settings.queue_name())
    monkeypatch.setenv("ORCAN_NAMED_INSTANCE", "beta")
    second = (settings.state_dir(), settings.queue_name())
    assert first[0] != second[0] and first[1] != second[1]


def test_duplicate_active_delivery_cannot_start_a_second_attempt(repo):
    import fcntl

    from orcan_executor.settings import state_dir

    job = submit(repo)
    directory = state_dir() / "jobs" / job["id"]
    directory.mkdir(parents=True)
    with (directory / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        assert engine.run_job(job["id"]) is None
        assert store.get(job["id"])["attempts"] == 0
    assert engine.run_job(job["id"])["status"] == "passed"


def test_failed_procedure_archives_diagnostics_before_checkout_cleanup(repo):
    import sys

    config = json.loads((repo / profiles.CONFIG).read_text())
    config["profiles"]["selected"]["steps"] = [
        {
            "argv": [
                sys.executable,
                "-c",
                'from pathlib import Path; import sys; Path("diagnostic.txt").write_text("full trace" * 10000); sys.exit(1)',
                "{tests}",
            ]
        }
    ]
    config["profiles"]["selected"]["artifacts"] = ["diagnostic.txt"]
    (repo / profiles.CONFIG).write_text(json.dumps(config))
    (repo / ".gitignore").write_text("diagnostic.txt\n")
    commit(repo)
    event = engine.run_job(submit(repo)["id"])
    assert event["status"] == "failed"
    artifact = Path(event["report"]).parent / "artifacts/diagnostic.txt"
    assert artifact.stat().st_size == 100000
    assert "full trace" not in json.dumps(event)


def test_parallel_first_submissions_do_not_race_schema_initialization(repo):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = list(pool.map(lambda _: submit(repo), range(20)))
    assert len({job["id"] for job in jobs}) == 20
    assert len(store.listing()) == 20
