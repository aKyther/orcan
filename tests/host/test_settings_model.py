"""Settings drafts preserve custom image sources and require an explicit guarded save."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from ._scripts_loader import load_script

# Imported through the UI module to exercise its standalone host import boundary.
tui=load_script('settings_tui.py')
SettingsModel=tui.SettingsModel


def make_model(tmp_path, **extra):
    path=tmp_path/'orcan.config.json'
    path.write_text(json.dumps({'workspaces':[{'name':'keep','projects':[]}],**extra}))
    return SettingsModel(path)


def test_draft_cancel_does_not_write_and_keeps_workspace_metadata(tmp_path):
    model=make_model(tmp_path,executor={'workers':3})
    original=model.path.read_bytes()
    model.toggle_plugin('redis')
    model.toggle_agent('codex')
    assert model.dirty
    assert model.path.read_bytes()==original
    assert model.data['workspaces']==model.original['workspaces']
    assert 'orcan build' in model.next_actions()
    assert any('plugins.redis.enabled' in line for line in model.review())


def test_explicit_save_migrates_plugin_settings_and_reports_build_steps(tmp_path):
    model=make_model(tmp_path,executor={'workers':3},ttyd={'host_port':17682})
    model.toggle_plugin('redis')
    model.toggle_agent('codex')
    actions=model.save()
    cfg=json.loads(model.path.read_text())
    assert cfg['plugins']['redis']['enabled'] is True
    assert cfg['plugins']['redis']['workers']==3
    assert cfg['plugins']['ttyd']['host_port']==17682
    assert cfg['build']['agents']==['codex']
    assert cfg['workspaces']==[{'name':'keep','projects':[]}]
    assert 'executor' not in cfg and 'ttyd' not in cfg
    assert 'orcan build' in actions
    assert not model.dirty


def test_pinned_agents_and_custom_sources_survive_other_selections(tmp_path):
    source={'type':'npm','package':'@company/codex','registry':'https://npm.example.test'}
    entry={'name':'codex','version':'1.2.3','source':source}
    model=make_model(tmp_path,build={'agents':[entry],'tools':[{'name':'go','image':'golang:1.27-bookworm'}]})
    model.toggle_agent('claude')
    model.set_agent_version('claude','stable')
    model.toggle_tool('rust')
    model.save()
    assert model.data['build']['agents'][0]==entry
    assert model.data['build']['tools'][0]=={'name':'go','image':'golang:1.27-bookworm'}
    assert model.agents()['claude']['version']=='stable'


def test_rejects_empty_image_selection_and_invalid_runtime_settings(tmp_path):
    model=make_model(tmp_path,build={'agents':['codex'],'tools':[]})
    model.toggle_agent('codex')
    before=model.path.read_bytes()
    with pytest.raises(ValueError,match='at least one agent'):model.save()
    assert model.path.read_bytes()==before
    with pytest.raises(ValueError):model.set_tmux('initial_windows',99)
    with pytest.raises(ValueError):model.set_resource('cpus',-1)


def test_guarded_save_preserves_concurrent_workspace_edits(tmp_path):
    model=make_model(tmp_path)
    model.toggle_plugin('ssh')
    external={'workspaces':[{'name':'changed elsewhere','projects':[]}]}
    model.path.write_text(json.dumps(external))
    with pytest.raises(ValueError,match='changed'):model.save()
    assert json.loads(model.path.read_text())==external


def test_tui_lists_plugin_groups_agents_and_image_build_requirement(tmp_path):
    model=make_model(tmp_path,build={'agents':['codex'],'tools':[]})
    assert any('Access /' in row[1] for row in tui.rows(model,'plugins'))
    assert any('Services /' in row[1] for row in tui.rows(model,'plugins'))
    assert any('Interface /' in row[1] for row in tui.rows(model,'plugins'))
    assert ('agent:codex','[x] codex','latest') in tui.rows(model,'agents')
    model.toggle_agent('claude')
    assert 'orcan build' in model.next_actions()


def test_review_and_display_do_not_emit_terminal_control_characters(tmp_path):
    model=make_model(tmp_path)
    model.set_plugin('ttyd','font_family','text\x1b[2J')
    assert '\x1b' not in tui.safe_text(model.review())


def test_related_plugin_fields_can_be_edited_before_final_validation(tmp_path):
    model=make_model(tmp_path,plugins={'redis':{'workers':3}})
    model.set_plugin('redis','split_lanes',True)
    assert model.plugins()['redis']['workers']==3
    assert tui.rows(model,'plugin:redis')
    with pytest.raises(ValueError):model.save()
    model.set_plugin('redis','workers',1)
    model.save()
    assert model.plugins()['redis']['split_lanes'] is True
