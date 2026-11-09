"""Draft isolation, mixed project modes, validation and filesystem save boundaries."""
import argparse
import json
from pathlib import Path

import pytest

from ._scripts_loader import load_script

model = load_script('workspace_draft.py')
ui = load_script('workspace_editor.py')


@pytest.fixture
def draft(tmp_path, monkeypatch):
    monkeypatch.setenv('ORCAN_HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('ORCAN_DATA', str(tmp_path / 'home'))
    monkeypatch.setenv('ORCAN_PROJECTS_ROOT', str(tmp_path / 'sandbox'))
    monkeypatch.delenv('ORCAN_NAMED_INSTANCE', raising=False)
    return model.WorkspaceDraft(tmp_path / 'home' / 'orcan.config.json')


def test_empty_workspace_and_multi_selection_stay_in_memory(draft, tmp_path):
    ws = draft.add_workspace('daily')
    paths = [tmp_path / name for name in ['api', 'web', 'assets']]
    for path in paths:
        path.mkdir()
    draft.add_projects(ws, paths)
    draft.add_projects(ws, paths[:1])
    assert [p['name'] for p in ws['projects']] == ['api', 'web', 'assets']
    assert all(p['_mode'] == 'mount' for p in ws['projects'])
    assert draft.dirty
    assert not draft.path.exists()
    assert not (tmp_path / 'sandbox').exists()
    draft.remove_workspace(ws)
    assert not draft.workspaces
    assert all(path.is_dir() for path in paths)


@pytest.mark.integration
def test_save_empty_workspace_preserves_other_settings(draft):
    draft.data['resources'] = {'memory': '6g'}
    draft.add_workspace('empty')
    draft.save()
    assert json.loads(draft.path.read_text()) == {'resources': {'memory': '6g'}, 'workspaces': [{'name': 'empty', 'projects': []}]}
    assert not draft.dirty


@pytest.mark.integration
def test_mixed_modes_and_individual_branches_are_created_only_on_save(draft, tmp_path, tracked_git_repo_factory):
    api = tracked_git_repo_factory(tmp_path / 'api')
    web = tracked_git_repo_factory(tmp_path / 'web')
    assets = tmp_path / 'assets'
    assets.mkdir()
    ws = draft.add_workspace('daily')
    draft.add_projects(ws, [api, web, assets])
    for project, branch in zip(ws['projects'][:2], ['feature/api', 'feature/ui']):
        project['_mode'] = 'worktree'
        project['_branch'] = branch
    assert not draft.path.exists()
    draft.validate()
    assert not (tmp_path / 'sandbox').exists()
    draft.save()
    projects = json.loads(draft.path.read_text())['workspaces'][0]['projects']
    assert projects[2]['path'] == str(assets)
    for project, branch in zip(projects[:2], ['feature/api', 'feature/ui']):
        path = Path(project['path'])
        assert path.is_dir()
        assert model.find_worktree_by_branch(api if project['name'] == 'api' else web, branch).path == path
    assert all(not any(key.startswith('_') for key in p) for p in projects)
    assert not draft.dirty


@pytest.mark.integration
def test_invalid_second_branch_prevents_all_creation(draft, tmp_path, tracked_git_repo_factory):
    repos = [tracked_git_repo_factory(tmp_path / name) for name in ['api', 'web']]
    ws = draft.add_workspace('daily')
    draft.add_projects(ws, repos)
    for project, branch in zip(ws['projects'], ['feature/valid', 'bad branch']):
        project.update(_mode='worktree', _branch=branch)
    with pytest.raises(ValueError, match='Invalid branch'):
        draft.save()
    assert not draft.path.exists()
    assert not (tmp_path / 'sandbox').exists()
    assert model.find_worktree_by_branch(repos[0], 'feature/valid') is None


def test_concurrent_edit_is_not_overwritten(draft):
    draft.add_workspace('daily')
    draft.path.parent.mkdir()
    draft.path.write_text('{"workspaces":[],"timezone":"UTC"}')
    before = draft.path.read_bytes()
    with pytest.raises(ValueError, match='another session'):
        draft.save()
    assert draft.path.read_bytes() == before


@pytest.mark.integration
def test_partial_creation_is_retained_and_reused_on_retry(draft, tmp_path, tracked_git_repo_factory, monkeypatch):
    repos = [tracked_git_repo_factory(tmp_path / name) for name in ['api', 'web']]
    ws = draft.add_workspace('daily')
    draft.add_projects(ws, repos)
    for project in ws['projects']:
        project.update(_mode='worktree', _branch='feature/daily')
    create = model.create_worktree
    calls = []
    def fail_second(repo, **kwargs):
        calls.append(repo)
        if len(calls) == 2:
            raise ValueError('simulated creation failure')
        return create(repo, **kwargs)
    monkeypatch.setattr(model, 'create_worktree', fail_second)
    with pytest.raises(ValueError, match='simulated'):
        draft.save()
    assert not draft.path.exists()
    assert len(draft.created) == 1
    draft.save()
    assert calls == [repos[0], repos[1], repos[1]]
    assert draft.path.exists()


@pytest.mark.integration
def test_workspace_delete_removes_entries_but_mount_directory_survives(draft, tmp_path):
    mount = tmp_path / 'assets'
    mount.mkdir()
    ws = draft.add_workspace('daily')
    draft.add_projects(ws, [mount])
    draft.save()
    draft.remove_workspace(draft.workspaces[0], delete_worktrees=True)
    assert json.loads(draft.path.read_text())['workspaces']
    draft.save()
    assert json.loads(draft.path.read_text())['workspaces'] == []
    assert mount.is_dir()


def test_vertical_rows_expose_project_actions_and_independent_modes(draft, tmp_path):
    ws = draft.add_workspace('daily')
    for name in ['api', 'assets']:
        (tmp_path / name).mkdir()
    draft.add_projects(ws, [tmp_path / 'api', tmp_path / 'assets'])
    ws['projects'][0].update(_mode='worktree', _branch='feature/api')
    rows = ui.editor_rows(draft, ws)
    labels = [row[1] for row in rows]
    assert labels.index('WORKSPACE') < labels.index('PROJECTS') < labels.index('SUMMARY — ALL WORKSPACES')
    assert any('api — Worktree / feature/api' in label for label in labels)
    assert any('assets — Mount as-is' in label for label in labels)
    assert all(key in [row[0] for row in rows] for key in ['name', 'add', 'delete', 'save', 'back'])


def test_new_workspace_cancel_does_not_write(draft, monkeypatch):
    import curses
    context = load_script('context_tui.py')
    monkeypatch.setattr(context, '_init_curses_session', lambda: None)
    # run() imports the canonical shared module, not this test loader alias.
    import context_tui
    monkeypatch.setattr(context_tui, '_init_curses_session', lambda: None)
    monkeypatch.setattr(context_tui, '_prompt_line', lambda *args: 'daily')
    monkeypatch.setattr(context_tui, '_confirm_line', lambda *args: True)
    monkeypatch.setattr(curses, 'curs_set', lambda *args: None)
    class Screen:
        def __init__(self):
            self.keys = iter([10, 27, 27])
            self.frames = []
        def getmaxyx(self): return 28, 100
        def erase(self): self.lines = []
        def addnstr(self, row, col, text, *args): self.lines.append(text)
        def refresh(self): self.frames.append('\n'.join(self.lines))
        def getch(self): return next(self.keys)
        def keypad(self, value): pass
    screen = Screen()
    assert ui.run(screen, draft, argparse.Namespace(workspace='', dir='')) == 1
    assert 'Name: daily' in screen.frames[1]
    assert '+ Add projects' in screen.frames[1]
    assert not draft.path.exists()


@pytest.mark.integration
@pytest.mark.parametrize('open_with_enter', [False, True])
def test_picker_arrow_navigation_keeps_selection_across_folders(tmp_path, open_with_enter):
    import curses
    # First choose a folder, descend, choose its child, go back, then add both.
    parent = tmp_path / 'projects'
    folder = parent / 'group'
    child = folder / 'api'
    child.mkdir(parents=True)
    class Screen:
        def __init__(self):
            self.keys = iter([ord(' '), 10 if open_with_enter else curses.KEY_RIGHT, ord(' '), curses.KEY_LEFT, curses.KEY_DOWN, 10])
            self.frames = []
        def getmaxyx(self): return 32, 120
        def erase(self): self.lines = []
        def addnstr(self, row, col, text, *args): self.lines.append(text)
        def refresh(self): self.frames.append('\n'.join(self.lines))
        def getch(self): return next(self.keys)
    screen = Screen()
    assert ui.pick_projects(screen, parent, set()) == [folder, child]
    assert 'Left: parent' in screen.frames[0]
    assert 'Right: open folder' in screen.frames[0]
    assert f'Folder: {folder}' in screen.frames[2]
    assert '2 selected' in screen.frames[4]
    assert '.. Return to parent folder' in screen.frames[0]
    assert 'Selected group.' in screen.frames[1]
    assert 'Opened group.' in screen.frames[2]
    assert 'Returned to parent folder' in screen.frames[4]
    assert 'SELECTED PROJECTS' in screen.frames[4]
    assert str(child) in screen.frames[4]


def test_sections_have_spacing_and_do_not_receive_focus(draft):
    import curses
    ws = draft.add_workspace('daily')
    rows = ui.editor_rows(draft, ws)
    # From workspace name, skip the PROJECTS heading and land on Add projects.
    assert rows[ui.move(rows, 1, 1)][0] == 'add'
    class Screen:
        def __init__(self): self.lines = {}
        def getmaxyx(self): return 36, 100
        def erase(self): self.lines = {}
        def addnstr(self, row, col, text, *args): self.lines[row] = text
        def refresh(self): pass
    screen = Screen()
    ui.frame(screen, 'Workspace', 'Draft', rows, 1)
    sections = [(row, text) for row, text in screen.lines.items() if '── ' in text]
    assert len(sections) == 3
    for row, _ in sections[1:]:
        assert screen.lines[row - 1] == ''
