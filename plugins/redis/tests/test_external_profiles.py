"""Orcan-owned procedure registries never modify the source project."""

import json
import shutil
import sys

from conftest import commit

from orcan_executor import cli, engine, notifications, profiles, snapshots, store


def external_project(repo):
    shutil.rmtree(repo / ".orcan")
    commit(repo)
    return repo


def register(repo, command=None):
    path = profiles.external_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    definition = {"steps": [{"argv": command or [sys.executable, "check.py"]}]}
    path.write_text(json.dumps({"version": 1, "profiles": {"quality": definition}}))
    return path, definition


def test_init_and_profiles_keep_project_clean(repo, capsys):
    external_project(repo)
    before = engine.git(repo, "status", "--porcelain")
    assert cli.main(["init", "--repo", str(repo), "--kind", "custom"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["config"] == str(profiles.external_path(repo))
    assert not profiles.external_path(repo).is_relative_to(repo)
    assert not (repo / ".orcan").exists()
    assert engine.git(repo, "status", "--porcelain") == before
    assert cli.main(["profiles", "--repo", str(repo)]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["config"] == result["config"]
    assert listed["profiles"] == ["quality"]


def test_submission_freezes_procedure_even_when_registry_changes(repo):
    external_project(repo)
    path, definition = register(repo)
    job = engine.submit(repo, "HEAD", "external", "quality", [], 20)
    assert job["profile_definition"] == definition
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "profiles": {
                    "quality": {"steps": [{"argv": [sys.executable, "-c", "raise SystemExit(19)"]}]}
                },
            }
        )
    )
    assert profiles.for_job(store.get(job["id"])) == definition
    engine.run_job(job["id"])
    completed = store.get(job["id"])
    assert completed["status"] == "passed"
    assert profiles.procedure_digest(definition) in notifications.message(completed)
    from orcan_executor.metrics import model_result

    compact = model_result(completed)
    assert "profile_definition" not in compact
    assert compact["procedure_sha256"] == profiles.procedure_digest(definition)
    assert not (repo / ".orcan").exists()
    assert not engine.git(repo, "status", "--porcelain")


def test_changed_procedure_does_not_join_same_sha_but_identical_one_does(repo):
    external_project(repo)
    register(repo)
    first = engine.submit(repo, "HEAD", "first", "quality", [], 20, reuse=True)
    joined = engine.submit(repo, "HEAD", "same", "quality", [], 20, reuse=True)
    assert joined["id"] == first["id"]
    register(repo, [sys.executable, "-c", "pass"])
    changed = engine.submit(repo, "HEAD", "different procedure", "quality", [], 20, reuse=True)
    assert changed["id"] != first["id"]
    assert changed["sha"] == first["sha"]


def test_registry_is_shared_by_worktrees_of_one_project(repo, tmp_path):
    sibling = tmp_path / "sibling"
    engine.git(repo, "worktree", "add", "--detach", str(sibling), "HEAD")
    assert profiles.external_path(repo) == profiles.external_path(sibling)


def test_directory_snapshot_uses_external_registry_without_adding_source_files(tmp_path):
    source = tmp_path / "directory"
    source.mkdir()
    (source / "run.py").write_text("print('small fixture')\n")
    path, definition = register(source, [sys.executable, "run.py"])
    with snapshots.snapshot(source, ["run.py"]) as repository:
        job = engine.submit(repository, "HEAD", "directory", "quality", [], 20)
        assert job["profile_definition"] == definition
        engine.run_job(job["id"])
        assert store.get(job["id"])["status"] == "passed"
    assert path.exists()
    assert sorted(p.name for p in source.iterdir()) == ["run.py"]


def test_directory_profiles_can_be_listed_before_a_git_repository_exists(tmp_path, capsys):
    source = tmp_path / "plain"
    source.mkdir()
    assert cli.main(["init", "--repo", str(source), "--kind", "custom"]) == 0
    capsys.readouterr()
    assert cli.main(["profiles", "--repo", str(source)]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert listing["sha"] is None
    assert listing["profiles"] == ["quality"]
    assert not list(source.iterdir())


def test_init_rejects_an_executor_state_directory_inside_the_project(repo, monkeypatch):
    import pytest

    monkeypatch.setenv("ORCAN_EXECUTOR_STATE_DIR", str(repo / "executor-state"))
    with pytest.raises(ValueError, match="outside the source"):
        profiles.external_path(repo)
    assert not (repo / "executor-state").exists()
