"""Mutable fixture isolation is required even when initialization is shared."""

import pytest

pytestmark = pytest.mark.integration


def test_git_repository_copies_do_not_share_config_or_files(
    tmp_path, git_repo_factory, git_template
):
    first = git_repo_factory(tmp_path / "first")
    second = git_repo_factory(tmp_path / "second")
    original = (second / ".git/config").read_bytes()
    (first / ".git/config").write_text("changed config")
    (first / "private.txt").write_text("only first")
    assert (second / ".git/config").read_bytes() == original
    assert (git_template / ".git/config").read_bytes() == original
    assert not (second / "private.txt").exists()
    assert not (git_template / "private.txt").exists()


def test_committed_copies_share_no_mutable_branches(
    tmp_path, committed_git_repo_factory, committed_git_template
):
    import subprocess

    first = committed_git_repo_factory(tmp_path / "first")
    second = committed_git_repo_factory(tmp_path / "second")
    subprocess.run(["git", "-C", str(first), "branch", "private"], check=True)
    for path in (second, committed_git_template):
        result = subprocess.run(
            ["git", "-C", str(path), "branch", "--list", "private"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout == ""
