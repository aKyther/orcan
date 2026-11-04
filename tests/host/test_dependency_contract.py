"""Shared requirements and plugin graph rules across settings/build/startup."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import pytest
from ._scripts_loader import load_script

ui = load_script('settings_tui.py')
from orcan.image_profile import resolve, requirements, BASE_COMPONENTS
from orcan.plugin_registry import catalog, change_selection, dependency_order, validate_selection

ROOT = Path(__file__).resolve().parents[2]


def test_required_runtimes_are_independent_of_optional_toolchains():
    profile = resolve({'build': {'agents': ['codex', 'claude'], 'tools': []}})
    report = requirements(profile)
    assert report['agents']['codex'] == ['node', 'npm']
    assert set(report['agents']['claude']) <= BASE_COMPONENTS
    assert report['optional_toolchains'] == []
    assert report['python_locks'] == ['cockpit/uv.lock', 'executor/uv.lock']
    assert all(set(entry.get('image_requires', [])) <= BASE_COMPONENTS for entry in catalog())


def test_transitive_selection_order_cycles_and_disabling_required_plugins():
    entries = [{'id':'service','requires':['transport']}, {'id':'transport','requires':['base']}, {'id':'base'}]
    assert [entry['id'] for entry in dependency_order(entries)] == ['base','transport','service']
    values = {entry['id']:{'enabled':False} for entry in entries}
    with pytest.raises(ValueError, match='requires'):
        validate_selection(values | {'service':{'enabled':True}}, entries)
    enabled = change_selection(values, 'service', True, entries)
    assert all(entry['enabled'] for entry in enabled.values())
    assert all(not entry['enabled'] for entry in values.values())
    with pytest.raises(ValueError, match='before disabling'):
        change_selection(enabled, 'base', False, entries)
    with pytest.raises(ValueError, match='Cyclic'):
        dependency_order([{'id':'a','requires':['b']},{'id':'b','requires':['a']}])


def test_settings_conflicts_do_not_silently_change_other_plugins(tmp_path):
    path=tmp_path/'orcan.config.json'
    path.write_text(json.dumps({'workspaces':[], 'plugins':{'docker':{'enabled':True}}}))
    model=ui.SettingsModel(path)
    with pytest.raises(ValueError, match='Disable'):
        model.toggle_plugin('network')
    assert model.plugins()['docker']['enabled']
    assert not model.plugins()['network']['enabled']


def test_tool_image_edit_is_validated_and_preserves_other_selections(tmp_path):
    path=tmp_path/'orcan.config.json'
    path.write_text(json.dumps({'workspaces':[], 'build':{'agents':['codex'],'tools':['go','rust']}}))
    model=ui.SettingsModel(path)
    model.set_tool_image('go','golang:1.27-bookworm')
    assert model.data['build']['tools'] == [{'name':'go','image':'golang:1.27-bookworm'}, 'rust']
    with pytest.raises(ValueError): model.set_tool_image('go','bad image;command')
    model.validate()


@pytest.mark.integration
def test_build_and_startup_preview_share_requirements_without_docker(tmp_path):
    path=tmp_path/'orcan.config.json'
    path.write_text(json.dumps({'workspaces':[], 'build':{'agents':['codex'],'tools':[]},
                                'plugins':{'redis':{'enabled':True}}}))
    env={**os.environ,'ORCAN_HOME':str(tmp_path),'ORCAN_CONFIG_FILE':str(path),'CONFIG':str(path)}
    def report(arguments):
        result=subprocess.run(['bash',str(ROOT/'bin/orcan'), *arguments],env=env,capture_output=True,text=True)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    build=report(['build','--plan'])
    up=report(['up','--plan','--json'])
    assert build['requirements']['agents'] == up['requirements']['agents']
    assert up['requirements']['plugins']['redis']['image'] == ['redis','python','uv','supervisor']
    assert not (tmp_path/'mounts').exists()


@pytest.mark.integration
@pytest.mark.parametrize('flag,expected', [('', 'reused'), ('--force', 'built'), ('--no-cache','built')])
def test_build_reuses_current_selection_unless_explicitly_forced(tmp_path, flag, expected):
    path=tmp_path/'orcan.config.json'
    path.write_text('{"build":{"agents":["codex"],"tools":[]}}')
    script='''set -Eeuo pipefail
source cli/lib/common.sh
source cli/commands/build.sh
orcan_require_docker() { :; }; orcan_require_config_for_build() { :; }; orcan_load_config() { :; }
orcan_image_build_is_current() { return 0; }
orcan_ok() { echo reused; }
orcan_image_build_local() { echo built; }
orcan_image_record_build() { :; }
orcan_cmd_build '''+flag
    result=subprocess.run(['bash','-c',script],cwd=ROOT,
        env={**os.environ,'ORCAN_HOME':str(tmp_path),'CONFIG':str(path)},capture_output=True,text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


def test_catalog_rejects_unavailable_image_dependencies(tmp_path):
    package=tmp_path/'fixture'
    package.mkdir()
    (package/'plugin.json').write_text(json.dumps({'id':'fixture','version':1,
        'group':'services','enabled':False,'fields':{},'help':['Fixture setup'],'examples':['{}'],'image_requires':['missing-component']}))
    with pytest.raises(ValueError, match='unavailable image component'):
        catalog(tmp_path)
