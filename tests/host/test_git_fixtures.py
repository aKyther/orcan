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
