"""Bundled package rules govern selection, configuration and host lifecycle."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from orcan.plugin_registry import catalog, resolve

from ._scripts_loader import load_script

planner = load_script('plugin-plan.py')


def test_configured_plugins_and_settings_drive_plain_up():
    cfg = {'workspaces': [], 'plugins': {'redis': {'enabled': True, 'workers': 5, 'max_running': 5}, 'github': {'enabled': True, 'hostname': 'GITHUB.COMPANY.TEST'}}}
    result = planner.plan(cfg, [])
    assert result['with_redis'] == result['with_github'] == 1
    assert result['ORCAN_EXECUTOR_WORKERS'] == 5
    assert result['github_hostname'] == 'github.company.test'
    assert result['with_git'] == result['with_docker'] == 0


def test_cli_overrides_one_start_without_mutating_configuration():
    cfg = {'plugins': {'redis': {'enabled': True}}}
    original = copy.deepcopy(cfg)
    selected = planner.plan(cfg, ['--without', 'redis', '--with', 'ssh'])
    assert selected['with_redis'] == 0 and selected['with_git'] == 1
    assert cfg == original
    assert planner.plan(cfg, [])['with_redis'] == 1


@pytest.mark.parametrize('new,old', [('--with redis','--with-redis'),('--with executor','--with-executor'),('--with ssh','--with-git'),('--with github','--github'),('--with ttyd','--web-terminal')])
def test_legacy_flags_select_the_same_package(new, old):
    first,second = planner.plan({},new.split()),planner.plan({},old.split())
    assert first['ORCAN_PLUGINS_JSON'] == second['ORCAN_PLUGINS_JSON']


@pytest.mark.parametrize('cfg', [
    {'plugins': {'unknown': {'enabled':True}}},
    {'plugins': {'ssh': True}},
    {'plugins': {'ssh': {'enabled':'yes'}}},
    {'plugins': {'github': {'token':'must-not-be-persisted'}}},
    {'plugins': {'github': {'hostname':'https://example.test'}}},
    {'plugins': {'redis': {'workers':11}}},
    {'plugins': {'redis': {'split_lanes':True,'workers':2}}},
    {'plugins': {'executor': {},'redis': {}}},
])
def test_invalid_package_configuration_is_rejected(cfg):
    with pytest.raises(ValueError): resolve(cfg)


def test_conflicts_are_resolved_after_cli_can_disable_a_default():
    cfg = {'plugins': {'docker': {'enabled':True}, 'network': {'enabled':True,'name':'fixture'}}}
    with pytest.raises(ValueError,match='mutually exclusive'): planner.plan(cfg,[])
    assert planner.plan(cfg,['--without','docker'])['with_network'] == 1


def test_enabled_network_requires_a_name():
    with pytest.raises(ValueError,match='network name'):
        planner.plan({'plugins':{'network':{'enabled':True}}},[])


def test_resume_restores_the_resolved_plugins_without_credentials():
    selected = planner.plan({'plugins':{'redis':{'enabled':True,'workers':3}}},[])
    snapshot = json.loads(selected['ORCAN_PLUGINS_JSON'])
    resumed = planner.plan({'plugins':{'redis':{'enabled':False}}},['--resume'],{'plugins':snapshot})
    assert resumed['with_redis'] == 1
    assert resumed['ORCAN_EXECUTOR_WORKERS'] == 3
    assert 'ttyd_credential' not in snapshot


def test_auth_mode_is_transient_and_resume_requires_new_credential():
    selected = planner.plan({},['--web-terminal-auth','user:fixture-password'])
    assert 'fixture-password' not in selected['ORCAN_PLUGINS_JSON']
    with pytest.raises(ValueError,match='pass it again'):
        planner.plan({},['--resume'],{'plugins':json.loads(selected['ORCAN_PLUGINS_JSON']),'WITH_TTYD_AUTH':'1'})


def test_legacy_sections_supply_settings_but_do_not_enable_plugins():
    legacy = resolve({'executor':{'workers':4}, 'ttyd':{'host_port':17682}})
    assert legacy['redis']['workers'] == 4
    assert legacy['ttyd']['host_port'] == 17682
    assert legacy['redis']['enabled'] is False and legacy['ttyd']['enabled'] is False
    current = resolve({'executor':{'workers':4}, 'plugins':{'redis':{'workers':2}}})
    assert current['redis']['workers'] == 2


def test_plugin_settings_ui_groups_and_saves_selection_without_touching_workspaces(monkeypatch):
    wizard = load_script('settings-wizard.py')
    workspaces = [{'name':'keep','projects':[]}]
    cfg = {'workspaces':workspaces,'executor':{'workers':3},'ttyd':{'host_port':17682}}
    def answer(label, default=False):
        if label.startswith('Enable '): return '(redis)' in label or '(git)' in label
        return False
    monkeypatch.setattr(wizard,'ask_yes_no',answer)
    monkeypatch.setattr(wizard,'heading',lambda *args:None)
    assert wizard.edit_plugins(cfg)
    assert cfg['workspaces'] is workspaces
    assert cfg['plugins']['redis']['enabled'] is True
    assert cfg['plugins']['redis']['workers'] == 3
    assert cfg['plugins']['ttyd']['host_port'] == 17682
    assert 'executor' not in cfg and 'ttyd' not in cfg


def test_every_package_groups_rules_lifecycle_and_metadata():
    root = Path(__file__).resolve().parents[2] / 'plugins'
    for entry in catalog(root):
        package = root / entry['id']
        assert (package/'runtime.sh').is_file()
        assert 'Operating rules' in (package/'README.md').read_text()
        if 'compose' in entry: assert (package/entry['compose']).is_file()


def test_shared_schema_matches_package_fields():
    from orcan.plugin_registry import configuration_schema
    root = Path(__file__).resolve().parents[2]
    assert json.loads((root/'orcan.config.schema.json').read_text())['properties']['plugins'] == configuration_schema()


@pytest.mark.parametrize('name,updates', [
    ('ttyd', {'port':8080, 'host_port':8081, 'bind':'127.0.0.1', 'font_size':22, 'renderer':'canvas'}),
    ('redis', {'workers':1, 'max_running':2, 'max_pending':40, 'timeout_seconds':900, 'retention_seconds':7200}),
])
def test_package_editor_saves_fields_and_migrates_legacy_settings(monkeypatch, name, updates):
    wizard = load_script('settings-wizard.py')
    workspaces = [{'name':'preserved','projects':[]}]
    cfg = {'workspaces':workspaces, name if name == 'ttyd' else 'executor': {}}
    fields = next(entry['fields'] for entry in catalog() if entry['id'] == name)
    answers = {rule['label']:str(updates[key]) for key,rule in fields.items() if key in updates}
    monkeypatch.setattr(wizard, 'ask', lambda label, default: answers.get(label, default))
    monkeypatch.setattr(wizard, 'ask_yes_no', lambda label, default=False: f'({name})' in label if label.startswith('Enable ') else label.startswith('Configure '))
    assert wizard.edit_plugins(cfg)
    assert cfg['workspaces'] is workspaces
    assert cfg['plugins'][name].items() >= updates.items()
    assert 'executor' not in cfg and 'ttyd' not in cfg


def test_package_editor_rejects_invalid_field_and_preserves_previous_value(monkeypatch):
    wizard = load_script('settings-wizard.py')
    cfg = {'plugins':{'ttyd':{'enabled':True, 'port':8080}}}
    monkeypatch.setattr(wizard, 'ask', lambda label, default: 'invalid' if label == 'Port' else default)
    monkeypatch.setattr(wizard, 'ask_yes_no', lambda label, default=False: '(ttyd)' in label if label.startswith('Enable ') else label.startswith('Configure '))
    assert wizard.edit_plugins(cfg)
    assert cfg['plugins']['ttyd']['port'] == 8080


@pytest.mark.integration
def test_redis_compose_passes_all_resolved_settings_into_container(tmp_path):
    import os
    import shutil
    import subprocess

    if not shutil.which('docker'):
        pytest.skip('Docker Compose is unavailable')
    version = subprocess.run(['docker', 'compose', 'version'], check=False, capture_output=True)
    if version.returncode:
        pytest.skip('Docker Compose is unavailable')
    root = Path(__file__).resolve().parents[2]
    planner = load_script('plugin-plan.py')
    configured = {'plugins': {'redis': {
        'enabled': True, 'workers': 2, 'max_running': 1, 'max_pending': 17,
        'log_limit_mb': 7, 'artifact_limit_mb': 8, 'detail_budget_mb': 9,
        'worktree_budget_mb': 1234, 'timeout_seconds': 91, 'retention_seconds': 125,
    }}}
    resolved = planner.plan(configured, [])
    base = tmp_path / 'base.yml'
    base.write_text('services:\n  orcan:\n    image: fixture\n')
    value = subprocess.run(
        ['docker', 'compose', '-f', str(base), '-f', str(root / 'plugins/redis/compose.yml'),
         'config', '--format', 'json'],
        env={**os.environ, **{k: str(v) for k, v in resolved.items()}, 'TTYD_CREDENTIAL': ''},
        check=True, capture_output=True, text=True,
    )
    container = json.loads(value.stdout)['services']['orcan']['environment']
    for entry in catalog():
        if entry['id'] == 'redis':
            for name, rule in entry['fields'].items():
                if name != 'port':
                    assert container[rule['env']] == str(resolved[rule['env']])



def test_legacy_worktree_budget_is_hidden_but_preserved_in_both_editors(tmp_path, monkeypatch):
    ui = load_script('settings_tui.py')
    wizard = load_script('settings-wizard.py')
    cfg = {'workspaces': [], 'plugins': {'redis': {'enabled': True, 'worktree_budget_mb': 1234}}}
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(cfg))
    model = ui.SettingsModel(path)
    rows = ui.detail_rows(model, 'plugin:redis')
    assert 'worktree_budget_mb' not in [row[0] for row in rows]
    prompts = []
    def ask(label, default):
        prompts.append(label)
        return default
    monkeypatch.setattr(wizard, 'ask', ask)
    monkeypatch.setattr(wizard, 'ask_yes_no', lambda label, default=False:
                        '(redis)' in label if label.startswith('Enable ') else label.startswith('Configure '))
    assert wizard.edit_plugins(cfg)
    assert not any('worktree' in label.lower() for label in prompts)
    assert cfg['plugins']['redis']['worktree_budget_mb'] == 1234
    assert planner.plan(cfg, [])['ORCAN_EXECUTOR_WORKTREE_BUDGET_MB'] == 1234
