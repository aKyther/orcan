"""Runtime access flags and host-specific GitHub credentials; all tokens are fixtures."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOKEN_VARIABLES = (
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GH_ENTERPRISE_TOKEN",
    "GITHUB_ENTERPRISE_TOKEN",
    "ORCAN_GITHUB_TOKEN",
    "GH_HOST",
)


@pytest.fixture
def shell(tmp_path: Path):
    tools = tmp_path / "tools"
    tools.mkdir()
    gh = tools / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$GH_CALLS"\n'
        'test -n "$GH_SAVED_FIXTURE" || exit 1\n'
        'printf "%s" "$GH_SAVED_FIXTURE"\n'
    )
    gh.chmod(0o755)
    env = {
        key: value for key, value in os.environ.items() if key not in TOKEN_VARIABLES
    }
    env.update(
        PATH=f"{tools}:{env['PATH']}",
        ORCAN_RUNTIME_DIR=str(tmp_path / "mounts"),
        GH_CALLS=str(tmp_path / "gh-calls"),
        GH_SAVED_FIXTURE="",
        GH_FIXTURE_SCRIPT=str(gh),
        ORCAN_ENV_FILE=str(tmp_path / "fixture.env"),
        ORCAN_ROOT=str(ROOT),
    )
    prefix = """
set -Eeuo pipefail
source cli/lib/compose.sh
source cli/commands/up.sh
# /tmp is noexec in some Orcan workspaces. Run the gh fixture via its shell.
env() {
    local args=() arg
    for arg; do
        if [[ "$arg" == gh ]]; then args+=(bash "$GH_FIXTURE_SCRIPT"); else args+=("$arg"); fi
    done
    command env "${args[@]}"
}
orcan_die() { printf '%s\\n' "$*" >&2; exit 1; }
orcan_usage_error() { orcan_die "$@"; }
orcan_info() { :; }
orcan_warn() { printf '%s\\n' "$*" >&2; }
orcan_ok() { :; }
orcan_require_docker() { :; }
orcan_require_generated() { :; }
orcan_load_env() { :; }
orcan_maybe_hint_upgrade() { :; }
orcan_compose_ttyd_down_all_variants() { printf 'STOP\\n'; }
orcan_compose_up_run() { printf 'RUN %s %s %s %s %s %s\\n' "$1" "$2" "$3" "$4" "$5" "$6"; }
orcan_terminal_url() { printf 'http://fixture.test'; }
orcan_write_git_overlay() { printf '/fixture/ssh'; }
docker() { printf 'orcan-1 '; }
"""

    def run(script: str, **variables: str):
        return subprocess.run(
            ["bash", "-c", prefix + script],
            cwd=ROOT,
            env={**env, **variables},
            text=True,
            capture_output=True,
            check=False,
        )

    return run


@pytest.mark.parametrize(
    "hostname,variable",
    [
        ("github.com", "GH_TOKEN"),
        ("company.ghe.com", "GH_TOKEN"),
        ("github.company.test", "GH_ENTERPRISE_TOKEN"),
    ],
)
def test_matching_token_is_not_written_to_runtime_files(
    shell, tmp_path, hostname, variable
):
    result = shell(
        f"orcan_cmd_up --github --github-hostname {hostname}",
        **{variable: "fixture-right-token", "GH_SAVED_FIXTURE": "fixture-saved-token"},
    )
    assert result.returncode == 0, result.stderr
    assert "RUN 0 0 0 0 1 up" in result.stdout
    files = list((tmp_path / "mounts").iterdir())
    for file in files:
        assert "fixture-right-token" not in file.read_text()
    overlay = (tmp_path / "mounts/compose-github.generated.yml").read_text()
    assert f'{variable}: "${{ORCAN_GITHUB_TOKEN:-}}"' in overlay
    assert f'GH_HOST: "{hostname}"' in overlay
    assert not (tmp_path / "gh-calls").exists()
    assert "fixture-right-token" not in result.stdout + result.stderr


def test_wrong_token_family_is_not_reused_and_missing_auth_does_not_stop(
    shell, tmp_path
):
    result = shell(
        "orcan_cmd_up --github --github-hostname github.company.test",
        GH_TOKEN="fixture-cloud-token",
    )
    assert result.returncode != 0
    assert "GH_ENTERPRISE_TOKEN" in result.stderr
    assert "STOP" not in result.stdout
    assert not (tmp_path / "mounts").exists()
    assert (
        tmp_path / "gh-calls"
    ).read_text().strip() == "auth token --hostname github.company.test"


def test_saved_login_and_resume_resolve_the_exact_host_again(shell, tmp_path):
    result = shell(
        "orcan_cmd_up --github --github-hostname GITHUB.COMPANY.TEST\n"
        "orcan_cmd_up --resume\n",
        GH_SAVED_FIXTURE="fixture-saved-token",
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "gh-calls").read_text().splitlines() == [
        "auth token --hostname github.company.test",
        "auth token --hostname github.company.test",
    ]
    assert (
        "GITHUB_HOSTNAME=github.company.test"
        in (tmp_path / "mounts/last-up.env").read_text()
    )
    assert "fixture-saved-token" not in result.stdout + result.stderr


def test_no_github_and_old_resume_do_not_request_authentication(shell, tmp_path):
    runtime = tmp_path / "mounts"
    runtime.mkdir()
    (runtime / "last-up.env").write_text("WITH_GIT=0\nWITH_TTYD=0\n")
    result = shell(
        "orcan_cmd_up --resume\norcan_cmd_up\n", GH_TOKEN="fixture-inherited-token"
    )
    assert result.returncode == 0, result.stderr
    assert "RUN 0 0 0 0 0 up" in result.stdout
    assert not (tmp_path / "gh-calls").exists()
    assert not (runtime / "compose-github.generated.yml").exists()


def test_plain_start_disables_previously_requested_github(shell, tmp_path):
    result = shell("orcan_cmd_up --github\norcan_cmd_up\n", GH_TOKEN="fixture-token")
    assert result.returncode == 0, result.stderr
    assert "RUN 0 0 0 0 0 up" in result.stdout
    assert "WITH_GITHUB=0" in (tmp_path / "mounts/last-up.env").read_text()


@pytest.mark.parametrize(
    "args",
    [
        "--github-hostname github.company.test",
        "--github --github-hostname",
        "--github --github-hostname https://github.company.test",
        "--github --github-hostname 'host;touch /tmp/unwanted'",
        "--github --github-hostname host:8443",
        "--resume --github",
        "--web-terminal --with-ttyd-auth user:fixture",
        "--docker-socket --with-network fixture",
    ],
)
def test_invalid_or_conflicting_flags_fail_before_lifecycle(shell, args):
    result = shell(f"orcan_cmd_up {args}")
    assert result.returncode != 0
    assert "STOP" not in result.stdout


@pytest.mark.parametrize(
    "new,old",
    [
        ("--ssh", "--with-git"),
        ("--web-terminal", "--with-ttyd"),
        ("--web-terminal-auth user:fixture", "--with-ttyd-auth user:fixture"),
        ("--network fixture", "--with-network fixture"),
    ],
)
def test_old_aliases_keep_the_same_runtime_flags(shell, new, old):
    modern, legacy = shell(f"orcan_cmd_up {new}"), shell(f"orcan_cmd_up {old}")
    assert modern.returncode == legacy.returncode == 0
    assert [line for line in modern.stdout.splitlines() if line.startswith("RUN")] == [
        line for line in legacy.stdout.splitlines() if line.startswith("RUN")
    ]


def test_trace_output_never_contains_token(shell):
    result = shell(
        "set -x\norcan_cmd_up --github\n", GH_TOKEN="fixture-sensitive-value"
    )
    assert result.returncode == 0, result.stderr
    assert "fixture-sensitive-value" not in result.stdout + result.stderr


def test_enterprise_token_is_not_used_for_github_com(shell):
    result = shell("orcan_cmd_up --github", GH_ENTERPRISE_TOKEN="fixture-enterprise")
    assert result.returncode != 0
    assert "set GH_TOKEN" in result.stderr
    assert "STOP" not in result.stdout


def test_resume_fails_before_stop_if_saved_login_is_no_longer_available(shell):
    result = shell(
        "orcan_cmd_up --github\nunset GH_TOKEN\norcan_cmd_up --resume\n",
        GH_TOKEN="fixture-token",
    )
    assert result.returncode != 0
    assert result.stdout.count("STOP") == 1


def test_compose_wrapper_includes_github_only_when_requested(shell):
    result = shell(
        "source cli/lib/compose.sh\n"
        "docker() { printf '%s\\n' \"$@\"; }\n"
        "orcan_compose_up_run 0 0 0 0 0 up -d\n"
        "orcan_compose_up_run 0 0 0 0 1 up -d\n"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("compose-github.generated.yml") == 1
    assert result.stdout.splitlines().count("up") == 2


@pytest.mark.parametrize("new,old", [("--docker-socket", "--with-docker")])
def test_docker_socket_alias_passes_parsing_before_docker_access(shell, new, old):
    for flag in (new, old):
        result = shell(
            "orcan_require_docker() { printf 'dependency-check\\n'; exit 7; }\n"
            f"orcan_cmd_up {flag}"
        )
        assert result.returncode == 7
        assert result.stdout.strip() == "dependency-check"


def test_compose_receives_the_selected_token_without_literal_overlay_values(
    shell, tmp_path
):
    # Real Compose config only; no Docker daemon access or container lifecycle.
    base = tmp_path / "compose.yml"
    base.write_text("services:\n  orcan:\n    image: busybox\n")
    result = shell(
        "orcan_prepare_github github.company.test\n"
        "command docker compose --env-file /dev/null -f "
        + shlex.quote(str(base))
        + ' -f "$(orcan_compose_github_file)" config --format json',
        GH_ENTERPRISE_TOKEN="fixture-enterprise-token",
        GH_TOKEN="fixture-cloud-token",
    )
    assert result.returncode == 0, result.stderr
    environment = json.loads(result.stdout)["services"]["orcan"]["environment"]
    assert environment["GH_HOST"] == "github.company.test"
    assert environment["GH_ENTERPRISE_TOKEN"] == "fixture-enterprise-token"
    assert environment["GH_TOKEN"] == ""
    assert (
        "fixture-enterprise-token"
        not in (tmp_path / "mounts/compose-github.generated.yml").read_text()
    )


def test_network_overlay_still_joins_both_networks(shell, tmp_path):
    base = tmp_path / "compose.yml"
    base.write_text("services:\n  orcan:\n    image: busybox\n")
    result = shell(
        "orcan_write_network_overlay fixture-network >/dev/null\n"
        "command docker compose --env-file /dev/null -f "
        + shlex.quote(str(base))
        + ' -f "$(orcan_compose_network_file)" config --format json'
    )
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)
    assert set(config["services"]["orcan"]["networks"]) == {"default", "orcan_ext"}
    assert config["networks"]["orcan_ext"]["name"] == "fixture-network"
    assert config["networks"]["orcan_ext"]["external"] is True
