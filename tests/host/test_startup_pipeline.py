"""Startup failures preserve the current instance; successful builds are reusable."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess

import pytest

from ._scripts_loader import load_script

ROOT = Path(__file__).resolve().parents[2]
state = load_script('startup-state.py')


def test_fingerprint_tracks_image_sources_and_modes_but_not_workspace_configuration(tmp_path):
    (tmp_path / 'Dockerfile').write_text('FROM fixture\n')
    source = tmp_path / 'cockpit/src/app.py'
    source.parent.mkdir(parents=True)
    source.write_text('version = 1')
    first = state.fingerprint(tmp_path, '{}', '1:1:1')
    (tmp_path / 'orcan.config.json').write_text('{"workspaces":[]}')
    assert state.fingerprint(tmp_path, '{}', '1:1:1') == first
    source.chmod(0o755)
    assert state.fingerprint(tmp_path, '{}', '1:1:1') != first
    source.write_text('version = 2')
    assert state.fingerprint(tmp_path, '{}', '1:1:1') != first
    assert state.fingerprint(tmp_path, '{"agents":[]}', '1:1:1') != first


@pytest.mark.integration
def test_receipt_requires_exact_image_id_and_fingerprint(tmp_path):
    receipt = tmp_path / 'image-ready.json'
    command = ['python3', str(ROOT / 'scripts/repository/startup-state.py')]
    values = ['--file', str(receipt), '--fingerprint', 'source-a', '--image-id', 'sha256:a']
    subprocess.run(command + ['record'] + values, check=True)
    assert subprocess.run(command + ['matches'] + values).returncode == 0
    assert subprocess.run(command + ['matches'] + values[:-1] + ['sha256:b']).returncode != 0
    assert json.loads(receipt.read_text())['image_id'] == 'sha256:a'


def pipeline(tmp_path, fail):
    # Real up dispatch + stage ordering; all Docker/lifecycle operations are fake.
    script = r'''
set -Eeuo pipefail
source cli/commands/up.sh
orcan_host_python() { python3 "$@"; }
orcan_require_docker() { :; }
orcan_load_config() { :; }
orcan_maybe_hint_upgrade() { :; }
orcan_info() { :; }; orcan_ok() { :; }
orcan_usage_error() { return 2; }
orcan_startup_prepare() { echo prepare; [[ "$FAIL" != prepare ]]; }
orcan_startup_stage() { echo "stage:$1"; }
orcan_plugins_run() { echo "plugin:$1"; [[ "$FAIL" != "$1" ]]; }
orcan_run_selected() { echo "compose:$1"; [[ "$FAIL" != "$1" ]]; }
orcan_startup_verify() { echo verify; [[ "$FAIL" != verify ]]; }
orcan_compose_ttyd_down_all_variants() { echo DESTRUCTIVE_DOWN; return 99; }
orcan_write_up_state() { echo saved; }; orcan_write_last_up() { :; }
orcan_cmd_up
'''
    return subprocess.run(['bash', '-c', script], cwd=ROOT,
        env={**os.environ, 'ORCAN_ROOT': str(ROOT), 'ORCAN_SCRIPTS': str(ROOT / 'scripts/repository'),
             'ORCAN_HOME': str(tmp_path), 'ORCAN_RUNTIME_DIR': str(tmp_path / 'mounts'), 'FAIL': fail},
        capture_output=True, text=True)


@pytest.mark.integration
def test_preparation_and_compose_validation_fail_before_start(tmp_path):
    for failure in ('prepare', 'config'):
        result = pipeline(tmp_path, failure)
        assert result.returncode != 0, result.stderr
        assert 'compose:up' not in result.stdout
        assert 'DESTRUCTIVE_DOWN' not in result.stdout
        assert 'saved' not in result.stdout


@pytest.mark.integration
def test_readiness_failure_does_not_record_success(tmp_path):
    result = pipeline(tmp_path, 'verify')
    assert result.returncode != 0, result.stderr
    assert 'compose:up' in result.stdout
    assert 'saved' not in result.stdout


@pytest.mark.integration
def test_success_uses_compose_convergence_without_down(tmp_path):
    result = pipeline(tmp_path, '')
    assert result.returncode == 0, result.stderr
    assert result.stdout.index('compose:config') < result.stdout.index('compose:up')
    assert result.stdout.index('verify\n') < result.stdout.index('saved')
    assert 'stage:ready' in result.stdout
    assert 'DESTRUCTIVE_DOWN' not in result.stdout


@pytest.mark.integration
def test_real_preparation_reuses_build_after_later_failure_and_rebuilds_changed_source(tmp_path):
    root = tmp_path / 'source'
    (root / 'cli/commands').mkdir(parents=True)
    source = root / 'Dockerfile'
    source.write_text('FROM fixture')
    (root / 'cli/commands/build.sh').write_text('orcan_cmd_build() { echo build >> "$CALLS"; echo sha256:built > "$IMAGE"; }\n')
    runtime = tmp_path / 'runtime.json'
    runtime.write_text('{}')
    mounts = tmp_path / 'mounts.yml'
    mounts.write_text('services: {}')
    script = r'''
set -Eeuo pipefail
source "$LIBRARY"
source "$IMAGE_LIBRARY"
orcan_info() { :; }; orcan_load_config() { :; }; orcan_require_generated() { :; }
orcan_runtime_config_json_file() { echo "$RUNTIME"; }
orcan_runtime_compose_mounts_file() { echo "$MOUNTS"; }
orcan_runtime_config_is_stale() { return 1; }
orcan_config_path() { return 1; }
orcan_host_python() {
    if [[ "$1" == */image-profile.py ]]; then echo '{"agents":[]}'; else python3 "$@"; fi
}
docker() { [[ -f "$IMAGE" ]] && cat "$IMAGE"; }
orcan_startup_prepare
'''
    env = {**os.environ, 'LIBRARY': str(ROOT / 'cli/lib/startup.sh'), 'IMAGE_LIBRARY':str(ROOT / 'cli/lib/image.sh'), 'ORCAN_ROOT': str(root),
           'ORCAN_SCRIPTS': str(ROOT / 'scripts/repository'), 'ORCAN_RUNTIME_DIR': str(tmp_path / 'receipts'),
           'RUNTIME': str(runtime), 'MOUNTS': str(mounts), 'CALLS': str(tmp_path / 'calls'), 'IMAGE': str(tmp_path / 'image')}
    def run():
        result = subprocess.run(['bash', '-c', script], env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    run()
    # A failure in a later stage must not invalidate the completed image receipt.
    run()
    assert (tmp_path / 'calls').read_text().splitlines() == ['build']
    source.write_text('FROM changed-fixture')
    run()
    assert (tmp_path / 'calls').read_text().splitlines() == ['build', 'build']
