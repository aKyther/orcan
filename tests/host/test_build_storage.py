"""Storage diagnostics must not confuse source disks with remote builders."""
import json
import os
from pathlib import Path
import socket
import sys
import subprocess
import tempfile
import pytest
from ._scripts_loader import load_script

ROOT=Path(__file__).resolve().parents[2]
storage=load_script('build-storage.py')


def metadata(monkeypatch, *, free=3*1024**3, local=True, info=True):
    monkeypatch.delenv('DOCKER_HOST',raising=False)
    monkeypatch.delenv('DOCKER_CONTEXT',raising=False)
    def docker(*args):
        if args[0]=='info':return json.dumps({'root':'/fixture/docker','os':'Ubuntu','name':'fixture'}) if info else None
        if args==('context','show'):return 'default\n'
        if args[:2]==('context','inspect'):return json.dumps('unix:///var/run/docker.sock' if local else 'ssh://remote')
        if args[:2]==('buildx','inspect'):return 'Name: default\nDriver: docker\nEndpoint: default\n'
        if args[:2]==('system','df'):return '{"Type":"Images","Size":"9GB","Reclaimable":"1GB","Active":"2","TotalCount":"3"}\n'
        if args[:2]==('buildx','du'):return 'cache-id true 1GB\nShared:\t2GB\nPrivate:\t1GB\nReclaimable:\t3GB\nTotal:\t3GB\n'
        raise AssertionError('Unexpected Docker operation: '+str(args))
    monkeypatch.setattr(storage,'docker',docker)
    monkeypatch.setattr(storage.socket,'gethostname',lambda:'fixture')
    monkeypatch.setattr(storage.platform,'system',lambda:'Linux')
    monkeypatch.setattr(storage.Path,'exists',lambda self:False)
    monkeypatch.delenv('container',raising=False)
    def disk(path):return {'path':str(path),'free_bytes':free if str(path)=='/fixture/docker' else 123,'total_bytes':10*1024**3}
    monkeypatch.setattr(storage,'filesystem',disk)


def test_local_native_daemon_uses_its_own_filesystem_not_source(monkeypatch):
    metadata(monkeypatch)
    report=storage.inspect(Path('/source'))
    assert report['docker_disk']['free_bytes']==3*1024**3
    assert report['source_disk']['free_bytes']==123
    assert report['status']=='ok'
    assert report['builder_cache']['private']=='1GB'
    assert 'do not sum' in storage.render(report)


def test_low_verified_daemon_space_warns_and_allows_build(monkeypatch, capsys):
    metadata(monkeypatch,free=1024**3)
    report=storage.inspect(Path('/source'))
    assert report['status']=='low'
    assert 'Warning:' in storage.render(report)
    monkeypatch.setattr(sys,'argv',['build-storage.py','--root','/source'])
    assert storage.main()==0
    assert 'Warning:' in capsys.readouterr().out


@pytest.mark.parametrize('kind',['ssh','container','desktop','custom-builder','other-host'])
def test_unknown_builder_space_never_uses_local_source_free_space(monkeypatch,kind):
    metadata(monkeypatch,local=kind!='ssh')
    if kind=='container':monkeypatch.setenv('container','docker')
    if kind=='desktop':monkeypatch.setattr(storage.platform,'system',lambda:'Darwin')
    if kind=='custom-builder':
        real=storage.docker
        monkeypatch.setattr(storage,'docker',lambda *args:'Name: custom\nDriver: docker-container\nEndpoint: default\n' if args[:2]==('buildx','inspect') else real(*args))
    if kind=='other-host':monkeypatch.setattr(storage.socket,'gethostname',lambda:'different-host')
    report=storage.inspect(Path('/source'))
    assert report['docker_disk'] is None
    assert report['status']=='unknown'
    assert 'unverified' in storage.render(report)


def test_unavailable_daemon_is_reported_without_raw_auth_diagnostics(monkeypatch):
    metadata(monkeypatch,info=False)
    report=storage.inspect(Path('/source'))
    assert report['status']=='unavailable'
    assert 'Build stopped' in storage.render(report)


@pytest.mark.parametrize('context_override',[None,'selected'])
def test_docker_host_override_is_not_mistaken_for_local_context(monkeypatch,context_override):
    metadata(monkeypatch)
    monkeypatch.setenv('DOCKER_HOST','ssh://remote')
    if context_override:monkeypatch.setenv('DOCKER_CONTEXT',context_override)
    report=storage.inspect(Path('/source'))
    assert report['status']==('ok' if context_override else 'unknown')


@pytest.mark.integration
def test_daemon_failure_prevents_build_even_with_force(tmp_path):
    config=tmp_path/'config.json';config.write_text('{"build":{"agents":["codex"],"tools":[]}}')
    script='''set -Eeuo pipefail
source cli/lib/common.sh
source cli/commands/build.sh
orcan_require_docker() { :; }; orcan_require_config_for_build() { :; }; orcan_load_config() { :; }
orcan_image_build_is_current() { return 1; }
orcan_build_storage_check() { echo DAEMON_UNAVAILABLE; return 2; }
orcan_image_build_local() { echo BUILD_RAN; }
orcan_image_record_build() { echo RECEIPT_WRITTEN; }
orcan_cmd_build --force
'''
    result=subprocess.run(['bash','-c',script],cwd=ROOT,env={**os.environ,'CONFIG':str(config),'ORCAN_HOME':str(tmp_path)},capture_output=True,text=True)
    assert result.returncode==2,result.stderr
    assert result.stdout.strip()=='DAEMON_UNAVAILABLE'


@pytest.mark.integration
def test_explicit_storage_report_needs_no_config_and_creates_no_home(tmp_path):
    # Fake Docker lives on an executable filesystem; /tmp may be noexec.
    with tempfile.TemporaryDirectory(prefix='.orcan-test.',dir=ROOT) as directory:
        binary=Path(directory)/'docker'
        binary.write_text('''#!/usr/bin/env python3
import json,sys,socket
args=sys.argv[1:]
if args[0]=='compose':print('v2')
elif args[0]=='info':print(json.dumps({'root':'/fixture/docker','os':'Ubuntu','name':socket.gethostname()}))
elif args[:2]==['context','show']:print('default')
elif args[:2]==['context','inspect']:print(json.dumps('ssh://fixture'))
elif args[:2]==['buildx','inspect']:print('Name: default\\nDriver: docker\\nEndpoint: default')
elif args[:2]==['buildx','du']:print('Shared: 2GB\\nPrivate: 1GB\\nReclaimable: 3GB\\nTotal: 3GB')
elif args[:2]==['system','df']:print(json.dumps({'Type':'Images','Size':'9GB','Reclaimable':'1GB'}))
else:raise SystemExit(99)
''')
        binary.chmod(0o755)
        home=tmp_path/'absent-home'
        result=subprocess.run(['bash',str(ROOT/'bin/orcan'),'build','--check-space'],cwd=ROOT,
            env={**os.environ,'PATH':directory+os.pathsep+os.environ['PATH'],'ORCAN_HOME':str(home),'CONFIG':'','DOCKER_HOST':'ssh://fixture'},capture_output=True,text=True)
        assert result.returncode==0,result.stderr
        assert 'Build storage check' in result.stdout
        assert '9GB' in result.stdout and 'free space: unknown' in result.stdout
        assert not home.exists()


@pytest.mark.integration
def test_reusing_completed_image_skips_storage_queries(tmp_path):
    config=tmp_path/'config.json';config.write_text('{"build":{"agents":["codex"],"tools":[]}}')
    script='''set -Eeuo pipefail
source cli/lib/common.sh
source cli/commands/build.sh
orcan_require_docker() { :; }; orcan_require_config_for_build() { :; }; orcan_load_config() { :; }
orcan_image_build_is_current() { return 0; }
orcan_build_storage_check() { echo UNEXPECTED_STORAGE_QUERY; return 99; }
orcan_ok() { echo REUSED; }
orcan_cmd_build
'''
    result=subprocess.run(['bash','-c',script],cwd=ROOT,env={**os.environ,'CONFIG':str(config),'ORCAN_HOME':str(tmp_path)},capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='REUSED'
