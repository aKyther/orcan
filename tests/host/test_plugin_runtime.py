"""Bundled package rules govern selection, configuration and host lifecycle."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from orcan.plugin_registry import catalog, resolve, validate_selection
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


def test_shared_schema_and_executor_limits_match_package_fields():
    from orcan.plugin_registry import configuration_schema
    from orcan.executor_config import DEFAULTS, LIMITS, ENVIRONMENT
    root = Path(__file__).resolve().parents[2]
    assert json.loads((root/'orcan.config.schema.json').read_text())['properties']['plugins'] == configuration_schema()
    fields = next(entry for entry in catalog() if entry['id']=='redis')['fields']
    for key,value in DEFAULTS.items():
        assert fields[key]['default'] == value
        assert fields[key]['env'] == ENVIRONMENT[key]
        if key in LIMITS: assert (fields[key]['minimum'],fields[key]['maximum']) == LIMITS[key]
