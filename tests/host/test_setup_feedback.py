"""CLI setup failures must remain failures; all external boundaries are fixtures."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


@pytest.fixture
def shell(tmp_path):
    with tempfile.TemporaryDirectory(
        prefix=".orcan-test.setup-", dir=ROOT
    ) as executable:
        runtime = Path(executable) / "sync-runtime.sh"
        runtime.write_text("#!/bin/sh\necho prepared-fixture-runtime\n")
        runtime.chmod(0o700)
        common = r"""
source cli/commands/sync.sh
source cli/commands/init.sh
orcan_info(){ printf '%s\n' "$*"; }
orcan_warn(){ printf 'WARN %s\n' "$*" >&2; }
orcan_ok(){ printf 'OK %s\n' "$*"; }
orcan_require_python(){ :; }
orcan_require_docker(){ return "${DOCKER_MISSING:-0}"; }
orcan_config_path(){ return 1; }
orcan_load_config(){ :; }
orcan_container_name(){ printf fixture; }
orcan_image_agents_manifest(){ printf '{}'; }
orcan_host_python(){
 case "$1" in
  */reconcile-host.py) printf 'host fixture diagnostic\n'; return "${HOST_CODE:-0}";;
  */context_tui.py|*/config-wizard.py) printf 'editor fixture diagnostic\n'; return "${EDITOR_CODE:-0}";;
  *) :;;
 esac
}
docker(){
 case "$1" in
  ps) [ "${DOCKER_PS_CODE:-0}" = 0 ] || return "$DOCKER_PS_CODE"; [ "${RUNNING:-1}" = 0 ] || printf fixture;;
  exec) printf 'live fixture diagnostic\n'; return "${LIVE_CODE:-0}";;
 esac
}
"""

        def run(command, **environment):
            return subprocess.run(
                ["bash", "-c", common + command],
                cwd=ROOT,
                env={
                    **os.environ,
                    "ORCAN_HOME": str(tmp_path / "home"),
                    "ORCAN_RUNTIME_DIR": str(tmp_path / "home/mounts"),
                    "ORCAN_CONFIG_FILE": str(tmp_path / "home/orcan.config.json"),
                    "ORCAN_ROOT": str(ROOT),
                    "ORCAN_SCRIPTS": executable,
                    **environment,
                },
                capture_output=True,
                text=True,
                timeout=5,
            )

        yield run


@pytest.mark.parametrize("code", ["1", "2", "7"])
@pytest.mark.parametrize("mode", ["", " --cli"])
def test_init_editor_error_is_not_reported_as_cancellation(shell, code, mode):
    result = shell("orcan_cmd_init" + mode, EDITOR_CODE=code)
    assert result.returncode == int(code)
    assert "cancelled" not in result.stdout
    assert "init done" not in result.stdout
    assert "workspace editor failed" in result.stderr


@pytest.mark.parametrize("mode", ["", " --cli"])
def test_init_explicit_cancellation_is_a_clean_noop(shell, mode):
    result = shell("orcan_cmd_init" + mode, EDITOR_CODE="130")
    assert result.returncode == 0
    assert "cancelled" in result.stdout
    assert "init done" not in result.stdout


@pytest.mark.parametrize(
    "variable,code,detail",
    [
        ("HOST_CODE", "7", "host fixture diagnostic"),
        ("LIVE_CODE", "9", "live fixture diagnostic"),
    ],
)
def test_failed_reconcile_reports_partial_state_and_propagates_exit(
    shell, variable, code, detail
):
    result = shell("orcan_cmd_sync", **{variable: code})
    assert result.returncode == int(code)
    assert detail in result.stderr
    assert "sync complete" not in result.stdout
    assert "down &&" not in result.stderr
    if variable == "HOST_CODE":
        assert "live fixture diagnostic" not in result.stdout


def test_docker_state_failure_is_not_a_stopped_container(shell):
    result = shell("orcan_cmd_sync", DOCKER_PS_CODE="4")
    assert result.returncode != 0
    assert "could not be checked" in result.stderr
    assert "container not running" not in result.stdout


@pytest.mark.parametrize("running", ["0", "1"])
def test_success_distinguishes_prepared_metadata_and_live_runtime(shell, running):
    result = shell("orcan_cmd_sync", RUNNING=running)
    assert result.returncode == 0, result.stderr
    assert "sync complete" in result.stdout
    assert "orcan up --plan" in result.stdout
    assert ("live reconcile complete" in result.stdout) == (running == "1")
    assert "down && orcan up" not in result.stdout


def test_manifest_probe_forbids_implicit_pulls(tmp_path):
    calls = tmp_path / "calls"
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source cli/lib/image.sh; docker(){ printf "%s\\n" "$@" > "$CALLS"; return 1; }; orcan_image_agents_manifest fixture:missing',
        ],
        cwd=ROOT,
        env={**os.environ, "CALLS": str(calls)},
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    assert "--pull=never" in calls.read_text().splitlines()


def test_missing_image_metadata_is_visible_without_blocking_host_preparation(shell):
    result = shell("orcan_image_agents_manifest(){ :; }; orcan_cmd_sync", RUNNING="0")
    assert result.returncode == 0, result.stderr
    assert "installed clients were not confirmed" in result.stdout
    assert "host workspace reconcile complete" in result.stdout


def test_reconcile_diagnostics_are_bounded_but_keep_the_final_error(shell):
    result = shell(
        "orcan_host_python(){ printf 'detail-%s\\n' {1..40}; return 7; }; orcan_cmd_sync"
    )
    assert result.returncode == 7
    assert "detail-1\n" not in result.stderr
    assert "detail-20\n" not in result.stderr
    assert "detail-21\n" in result.stderr
    assert "detail-40\n" in result.stderr
