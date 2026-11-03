"""Startup preview must never mutate state, invoke Docker, or acquire credentials."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from ._scripts_loader import load_script

ROOT=Path(__file__).resolve().parents[2]
plan=load_script('up-plan.py')


def test_read_only_preview_reports_configured_agents_plugins_and_ports(tmp_path):
    path=tmp_path/'orcan.config.json'
    cfg={'workspaces':[],'build':{'agents':[{'name':'codex','version':'1.2.3'}],'tools':[]},'plugins':{'redis':{'enabled':True,'workers':5},'ttyd':{'enabled':True,'host_port':17681}}}
    path.write_text(json.dumps(cfg))
    before=path.read_bytes()
    report=plan.preview(path,tmp_path,[])
    assert report['read_only'] is True
    assert report['plugins']['redis']['workers']==5
    assert report['image']['requested_profile']['agents']==[{'name':'codex','version':'1.2.3'}]
    assert report['configuration']['needs_sync'] is True
    assert any(port['host']==17681 for port in report['ports'])
    assert path.read_bytes()==before
    assert not (tmp_path/'mounts').exists()


def test_auth_arguments_and_custom_agent_source_never_appear_in_plan(tmp_path):
    path=tmp_path/'orcan.config.json'
    cfg={'workspaces':[],'build':{'agents':[{'name':'codex','source':{'type':'npm','registry':'https://registry.example.test/private-query?key=fixture'}}],'tools':[]}}
    path.write_text(json.dumps(cfg))
    report=plan.preview(path,tmp_path,['--github','--web-terminal-auth','user:fixture-password'])
    text=json.dumps(report)+plan.render(report)
    assert 'fixture-password' not in text
    assert 'private-query' not in text
    assert len(report['credentials'])==2


def test_resume_previews_auth_requirement_without_reacquiring_password(tmp_path):
    path=tmp_path/'orcan.config.json';path.write_text('{"workspaces":[]}')
    state=tmp_path/'last-up.json';state.write_text('{"WITH_TTYD":"1","WITH_TTYD_AUTH":"1"}')
    report=plan.preview(path,tmp_path,['--resume'],state)
    assert 'ttyd' in report['enabled_plugins']
    assert any(entry['plugin']=='ttyd' for entry in report['credentials'])


@pytest.mark.integration
def test_cli_plan_is_read_only_even_when_configuration_home_does_not_exist(tmp_path):
    home=tmp_path/'not-created'
    # Shell functions are inherited by the CLI through BASH_ENV; none may run.
    guard=tmp_path/'guard.sh'
    guard.write_text('docker() { echo DOCKER_RAN >&2; return 99; }; gh() { echo AUTH_RAN >&2; return 99; }; glab() { echo AUTH_RAN >&2; return 99; }\n')
    env={**os.environ,'ORCAN_HOME':str(home),'ORCAN_CONFIG_FILE':str(home/'orcan.config.json'),'ORCAN_RUNTIME_DIR':str(home/'mounts'),'CONFIG':'','BASH_ENV':str(guard),'GH_TOKEN':'fixture-never-disclosed'}
    result=subprocess.run([str(ROOT/'bin/orcan'),'up','--plan','--json','--with','github'],cwd=ROOT,env=env,capture_output=True,text=True,check=False)
    assert result.returncode==0,result.stderr
    report=json.loads(result.stdout)
    assert report['configuration']['exists'] is False
    assert not home.exists()
    assert 'DOCKER_RAN' not in result.stderr and 'AUTH_RAN' not in result.stderr
    assert 'fixture-never-disclosed' not in result.stdout+result.stderr
