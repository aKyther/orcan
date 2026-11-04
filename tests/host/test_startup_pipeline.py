"""Startup failures preserve the current instance; successful builds are reusable."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import tempfile

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
orcan_startup_check_inputs() { echo prepare; [[ "$FAIL" != prepare ]]; }
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
@pytest.mark.parametrize('problem',['','generated','image'])
def test_up_checks_inputs_without_sync_build_or_pull(tmp_path,problem):
    calls=tmp_path/'calls'
    script=r'''
set -Eeuo pipefail
source "$LIBRARY"
orcan_load_config() { :; }
orcan_require_generated() { echo check-generated >> "$CALLS"; [[ "$PROBLEM" != generated ]]; }
orcan_warn() { echo "$*" >&2; }
orcan_cmd_sync() { echo UNEXPECTED_SYNC; return 99; }
orcan_cmd_build() { echo UNEXPECTED_BUILD; return 99; }
docker() {
    echo "$*" >> "$CALLS"
    [[ "$1 $2" == 'image inspect' ]] || { echo UNEXPECTED_DOCKER; return 99; }
    [[ "$PROBLEM" != image ]]
}
orcan_startup_check_inputs
'''
    result=subprocess.run(['bash','-c',script],env={**os.environ,'LIBRARY':str(ROOT/'cli/lib/startup.sh'),
        'CALLS':str(calls),'PROBLEM':problem},capture_output=True,text=True)
    assert (result.returncode==0)==(not problem),result.stderr
    assert 'UNEXPECTED' not in result.stdout
    invoked=calls.read_text()
    assert invoked.startswith('check-generated')
    if problem=='generated':assert 'image inspect' not in invoked
    elif problem=='image':assert 'orcan build' in result.stderr


@pytest.mark.integration
def test_every_selected_compose_up_forbids_implicit_builds_and_pulls():
    script='''set -Eeuo pipefail
source cli/lib/plugins.sh
with_docker=0 with_git=0 with_network=0 with_ttyd=0 with_github=0 with_gitlab=0
orcan_compose_up_run() { printf '%s\\n' "$*"; }
orcan_run_selected up -d --force-recreate
orcan_run_selected exec -T orcan test -d /tmp
'''
    result=subprocess.run(['bash','-c',script],cwd=ROOT,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    up,execute=result.stdout.splitlines()
    assert up.endswith('up -d --force-recreate --no-build --pull never')
    assert '--no-build' not in execute and '--pull' not in execute


@pytest.mark.integration
def test_actual_up_rejects_stale_files_without_sync_build_or_pull(tmp_path):
    home=tmp_path/'home';mounts=home/'mounts';mounts.mkdir(parents=True)
    config=home/'orcan.config.json'
    config.write_text(json.dumps({'workspaces':[], 'data_root':str(tmp_path/'data'),
        'projects_root':str(tmp_path/'projects'), 'plugins':{'git':{'enabled':False}}}))
    runtime=mounts/'runtime-config.json';runtime.write_text('{}')
    compose=mounts/'compose-projects.generated.yml';compose.write_text('services: {}')
    stamp=max(runtime.stat().st_mtime_ns,compose.stat().st_mtime_ns)+1000000
    os.utime(config,ns=(stamp,stamp))
    before=config.read_bytes(),runtime.read_bytes(),compose.read_bytes()
    calls=tmp_path/'docker-calls'
    with tempfile.TemporaryDirectory(prefix='.orcan-test.',dir=ROOT) as directory:
        binary=Path(directory)/'docker'
        binary.write_text('''#!/usr/bin/env python3
import os,sys
from pathlib import Path
with Path(os.environ['CALLS']).open('a') as stream:stream.write(' '.join(sys.argv[1:])+'\\n')
if sys.argv[1:3]==['compose','version']:print('v2')
else:raise SystemExit(98)
''')
        binary.chmod(0o755)
        result=subprocess.run(['bash',str(ROOT/'bin/orcan'),'up'],cwd=ROOT,
            env={**os.environ,'PATH':directory+os.pathsep+os.environ['PATH'],
                 'ORCAN_HOME':str(home),'ORCAN_RUNTIME_DIR':str(mounts),'ORCAN_CONFIG_FILE':str(config),
                 'CONFIG':str(config),'CALLS':str(calls)},capture_output=True,text=True)
    assert result.returncode!=0
    assert 'sync' in result.stderr
    assert (config.read_bytes(),runtime.read_bytes(),compose.read_bytes())==before
    assert calls.read_text().splitlines()==['compose version']
