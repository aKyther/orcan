"""Explicit integration boundaries; pure tests cannot launch external helpers."""

import shutil
import subprocess
import os

import pytest


@pytest.fixture(scope="session")
def git_template(tmp_path_factory):
    """Initialize once; consumers always receive a private copy, never a link."""
    path = tmp_path_factory.mktemp("git-template") / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    return path


@pytest.fixture
def git_repo_factory(git_template):
    def create(path):
        shutil.copytree(git_template, path)
        return path

    return create


@pytest.fixture(scope="session")
def committed_git_template(git_template, tmp_path_factory):
    path = tmp_path_factory.mktemp("git-committed-template") / "repo"
    shutil.copytree(git_template, path)
    environment = {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
    }
    for key, value in (
        ("user.name", "Test"),
        ("user.email", "test@example.test"),
        ("core.hooksPath", os.devnull),
    ):
        subprocess.run(
            ["git", "-C", str(path), "config", key, value], check=True, env=environment
        )
    subprocess.run(
        ["git", "-C", str(path), "commit", "--allow-empty", "-qm", "initial"],
        check=True,
        env=environment,
    )
    return path


@pytest.fixture
def committed_git_repo_factory(committed_git_template):
    def create(path):
        shutil.copytree(committed_git_template, path)
        return path

    return create


@pytest.fixture(scope="session")
def tracked_git_template(committed_git_template, tmp_path_factory):
    """A tracked README for tests that edit content, prepared only once."""
    path = tmp_path_factory.mktemp("git-tracked-template") / "repo"
    shutil.copytree(committed_git_template, path)
    (path / "README").write_text("x\n", encoding="utf-8")
    environment = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    subprocess.run(
        ["git", "-C", str(path), "add", "README"], check=True, env=environment
    )
    subprocess.run(
        ["git", "-C", str(path), "commit", "-qm", "tracked content"],
        check=True,
        env=environment,
    )
    return path


@pytest.fixture
def tracked_git_repo_factory(tracked_git_template):
    def create(path):
        shutil.copytree(tracked_git_template, path, dirs_exist_ok=True)
        return path

    return create


def reject_external_process(*args, **kwargs):
    raise AssertionError(
        "Pure tests cannot start subprocesses. Mock the boundary or mark this test integration."
    )


@pytest.fixture(autouse=True)
def pure_process_boundary(request, monkeypatch):
    if request.node.get_closest_marker("integration") is None:
        monkeypatch.setattr(subprocess, "Popen", reject_external_process)
