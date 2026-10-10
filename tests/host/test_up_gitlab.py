"""GitLab runtime access uses fixture credentials, never a real host login."""

import json
import shlex

import pytest

from tests.host.test_up_github import shell as shell  # noqa: PLC0414 — shared pytest fixture


@pytest.mark.parametrize("hostname", ["gitlab.com", "gitlab.company.test"])
def test_gitlab_token_works_for_public_and_company_hosts(shell, tmp_path, hostname):
    result = shell(
        f"orcan_cmd_up --gitlab --gitlab-hostname {hostname}",
        GITLAB_TOKEN="fixture-gitlab",
    )
    assert result.returncode == 0, result.stderr
    overlay = (tmp_path / "mounts/compose-gitlab.generated.yml").read_text()
    assert f'GITLAB_HOST: "{hostname}"' in overlay
    assert 'GITLAB_TOKEN: "${ORCAN_GITLAB_TOKEN:-}"' in overlay
    assert "WITH_GITLAB=1" in (tmp_path / "mounts/last-up.env").read_text()
    for file in (tmp_path / "mounts").iterdir():
        assert "fixture-gitlab" not in file.read_text()
    assert "fixture-gitlab" not in result.stdout + result.stderr
    assert not (tmp_path / "glab-calls").exists()


def test_saved_login_is_selected_by_host_and_resolved_again_on_resume(shell, tmp_path):
    result = shell(
        "orcan_cmd_up --gitlab --gitlab-hostname GITLAB.COMPANY.TEST\norcan_cmd_up --resume",
        GLAB_SAVED_FIXTURE="fixture-saved-gitlab",
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "glab-calls").read_text().splitlines() == [
        "config get token --host gitlab.company.test",
        "config get token --host gitlab.company.test",
    ]


@pytest.mark.parametrize(
    "args",
    [
        "--gitlab-hostname gitlab.company.test",
        "--gitlab --gitlab-hostname",
        "--gitlab --gitlab-hostname ''",
        "--gitlab --gitlab-hostname https://gitlab.company.test",
        "--gitlab --gitlab-hostname 'host;touch /tmp/unwanted'",
        "--resume --gitlab",
    ],
)
def test_invalid_flags_fail_before_stopping_container(shell, args):
    result = shell(f"orcan_cmd_up {args}")
    assert result.returncode != 0
    assert "STOP" not in result.stdout


def test_github_and_ci_job_tokens_are_not_used_for_gitlab(shell):
    result = shell(
        "orcan_cmd_up --gitlab", GH_TOKEN="fixture-github", CI_JOB_TOKEN="fixture-job"
    )
    assert result.returncode != 0
    assert "set GITLAB_TOKEN" in result.stderr
    assert "STOP" not in result.stdout


def test_missing_gitlab_auth_does_not_stop_when_github_is_also_enabled(shell):
    result = shell("orcan_cmd_up --github --gitlab", GH_TOKEN="fixture-github")
    assert result.returncode != 0
    assert "STOP" not in result.stdout


def test_plain_start_and_legacy_resume_leave_gitlab_disabled(shell, tmp_path):
    runtime = tmp_path / "mounts"
    runtime.mkdir()
    (runtime / "last-up.env").write_text("WITH_GIT=0\nWITH_GITHUB=0\n")
    result = shell(
        "orcan_cmd_up --resume\norcan_cmd_up", GITLAB_TOKEN="fixture-inherited"
    )
    assert result.returncode == 0, result.stderr
    assert "WITH_GITLAB=0" in (runtime / "last-up.env").read_text()
    assert not (runtime / "compose-gitlab.generated.yml").exists()
    assert not (tmp_path / "glab-calls").exists()


def test_plain_start_disables_previously_enabled_gitlab(shell, tmp_path):
    result = shell("orcan_cmd_up --gitlab\norcan_cmd_up", GITLAB_TOKEN="fixture-gitlab")
    assert result.returncode == 0, result.stderr
    assert "WITH_GITLAB=0" in (tmp_path / "mounts/last-up.env").read_text()


def test_tracing_does_not_print_gitlab_token(shell):
    result = shell(
        "set -x\norcan_cmd_up --gitlab", GITLAB_TOKEN="fixture-sensitive-gitlab"
    )
    assert result.returncode == 0, result.stderr
    assert "fixture-sensitive-gitlab" not in result.stdout + result.stderr


def test_github_and_gitlab_overlays_compose_together_with_distinct_tokens(
    shell, tmp_path
):
    base = tmp_path / "compose.yml"
    base.write_text("services:\n  orcan:\n    image: busybox\n")
    result = shell(
        "orcan_prepare_github github.com\norcan_prepare_gitlab gitlab.company.test\n"
        "command docker compose --env-file /dev/null -f "
        + shlex.quote(str(base))
        + ' -f "$(orcan_compose_github_file)" -f "$(orcan_compose_gitlab_file)" config --format json',
        GH_TOKEN="fixture-github",
        GITLAB_TOKEN="fixture-gitlab",
    )
    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout)["services"]["orcan"]["environment"]
    assert values["GH_TOKEN"] == "fixture-github"
    assert values["GITLAB_TOKEN"] == "fixture-gitlab"
    assert values["GITLAB_HOST"] == "gitlab.company.test"
    assert values["CI_JOB_TOKEN"] == ""
    assert values["GLAB_ENABLE_CI_AUTOLOGIN"] == "false"


def test_compose_wrapper_includes_gitlab_only_when_requested(shell):
    result = shell(
        'source cli/lib/compose.sh\ndocker() { printf "%s\\n" "$@"; }\n'
        "orcan_compose_up_run 0 0 0 0 0 0 up -d\n"
        "orcan_compose_up_run 0 0 0 0 1 1 up -d\n"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("compose-gitlab.generated.yml") == 1
    assert result.stdout.count("compose-github.generated.yml") == 1
