"""Selective explicit memory, provenance, concurrency guards and bounded output."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "docker/rootfs/usr/local/lib"))
from orcan import compact, memory


def test_retrieval_returns_relevant_notes_with_sources_and_budget(tmp_path):
    memory.remember(
        tmp_path,
        "tests",
        "Pytest setup",
        "Run selected pytest cases with locked uv dependencies.",
        ["pytest"],
        ["README.md:20"],
    )
    memory.remember(
        tmp_path,
        "ssh",
        "SSH transport",
        "SSH mounts require --with-ssh.",
        ["ssh"],
        ["docs/ssh.md"],
    )
    result = memory.search(tmp_path, "pytest", budget=1000)
    assert [v["id"] for v in result["matches"]] == ["tests"]
    assert result["matches"][0]["sources"] == ["README.md:20"]
    assert len(json.dumps(result, ensure_ascii=False).encode()) <= 1000
    assert memory.search(tmp_path, "unrelatedword")["matches"] == []


def test_updates_require_current_revision_and_refresh_index(tmp_path):
    first = memory.remember(tmp_path, "tests", "Tests", "pytest old", [], [])
    with pytest.raises(ValueError):
        memory.remember(tmp_path, "tests", "Tests", "new runner", [], [])
    memory.remember(tmp_path, "tests", "Tests", "new runner", [], [], first["sha256"])
    assert memory.search(tmp_path, "pytest")["matches"] == []
    assert memory.search(tmp_path, "runner")["matches"][0]["id"] == "tests"


def test_recap_updates_existing_brief_and_preserves_archive(tmp_path):
    (tmp_path / ".manifest.json").write_text("{}")
    candidate = tmp_path / "candidate"
    candidate.write_text("Current goal and next action")
    assert (
        memory.main(["--workspace", str(tmp_path), "recap", "--file", str(candidate)])
        == 0
    )
    current = compact.check(tmp_path)
    candidate.write_text(
        "Current goal, evidence, decisions and next action; this can be longer"
    )
    assert (
        memory.main(["--workspace", str(tmp_path), "recap", "--file", str(candidate)])
        == 2
    )
    assert (
        memory.main(
            [
                "--workspace",
                str(tmp_path),
                "recap",
                "--file",
                str(candidate),
                "--expected-sha256",
                current["sha256"],
            ]
        )
        == 0
    )
    assert "this can be longer" in compact.brief_path(tmp_path).read_text()
    assert any(
        "Current goal and next action" in p.read_text()
        for p in (tmp_path / ".orcan/brief-history").glob("*.md")
    )


def test_limits_and_symlink_guard(tmp_path):
    with pytest.raises(ValueError):
        memory.remember(tmp_path, "oversize", "Title", "x" * 8001, [], [])
    (tmp_path / ".orcan").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        memory.search(tmp_path, "query")


def test_forget_is_guarded_and_updates_search(tmp_path):
    note = memory.remember(tmp_path, "fact", "Fact", "Important build fact", [], [])
    with pytest.raises(ValueError):
        memory.forget(tmp_path, "fact", "stale")
    assert memory.forget(tmp_path, "fact", note["sha256"]) == {"removed": "fact"}
    assert memory.search(tmp_path, "build")["matches"] == []


@pytest.mark.integration
def test_project_memory_survives_task_worktree_removal(tmp_path):
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "Initial",
        ],
        check=True,
    )
    task = tmp_path / "task"
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "--detach", str(task)],
        check=True,
        capture_output=True,
    )
    shared = memory.project_store(task)
    memory.remember(
        shared, "fact", "Build", "Use the locked build profile", [], ["README.md"]
    )
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "remove", str(task)], check=True
    )
    assert memory.project_store(repo) == shared
    assert memory.search(shared, "profile")["matches"][0]["id"] == "fact"
