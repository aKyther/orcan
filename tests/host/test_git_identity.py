"""Container defaults must allow repository and conditional Git identities."""

import pytest

import os
import subprocess
from pathlib import Path

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


def test_host_identity_is_a_default(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        HOME=str(home),
        XDG_CONFIG_HOME=str(home / ".config"),
        GIT_CONFIG_NOSYSTEM="1",
        ORCAN_GIT_USER_NAME="Host User",
        ORCAN_GIT_USER_EMAIL="host@example.com",
    )
    entrypoint = (ROOT / "docker/rootfs/usr/local/bin/docker-entrypoint").read_text()
    start = entrypoint.index("    # Apply host identity")
    end = entrypoint.index("    # Parent for optional known_hosts", start)
    subprocess.run(
        ["bash", "-c", 'dotfiles="$HOME/dotfiles";\n' + entrypoint[start:end]],
        env=env,
        check=True,
    )

    def git(*args):
        return subprocess.check_output(
            ["git", *args], cwd=repo, env=env, text=True
        ).strip()

    git("init", "-q")
    for kind in ("AUTHOR", "COMMITTER"):
        assert git("var", f"GIT_{kind}_IDENT").startswith(
            "Host User <host@example.com>"
        )
    conditional = home / "work.gitconfig"
    conditional.write_text("[user]\n name = Work User\n email = work@example.com\n")
    git("config", "--global", f"includeIf.gitdir:{repo}/.git.path", str(conditional))
    for kind in ("AUTHOR", "COMMITTER"):
        assert git("var", f"GIT_{kind}_IDENT").startswith(
            "Work User <work@example.com>"
        )
    git("config", "--local", "user.name", "Repo User")
    git("config", "--local", "user.email", "repo@example.com")
    git("-c", "commit.gpgsign=false", "commit", "--allow-empty", "-qm", "Identity test")
    assert git("log", "-1", "--format=%an <%ae>|%cn <%ce>") == (
        "Repo User <repo@example.com>|Repo User <repo@example.com>"
    )


def test_compose_does_not_force_commit_identity():
    compose = (ROOT / "docker-compose.yml").read_text()
    assert "      ORCAN_GIT_USER_NAME: ${GIT_AUTHOR_NAME:-}" in compose
    assert "      ORCAN_GIT_USER_EMAIL: ${GIT_AUTHOR_EMAIL:-}" in compose
    for key in (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    ):
        assert f"      {key}:" not in compose
