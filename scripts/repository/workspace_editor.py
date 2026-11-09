"""Vertical terminal workspace editor with an explicit in-memory draft."""
from __future__ import annotations

import curses
from pathlib import Path

from context_selection import scan_dirs
from git_worktrees import is_git_repo, is_under_managed_root
from workspace_draft import WorkspaceDraft


def _text(value):
    return ''.join(c if c.isprintable() else ' ' for c in str(value))


def frame(screen, title, subtitle, items, cursor, message='', *, hint='Up/Down: choose   Enter: select   Esc: back', footer=None):
    """One column, with the selected action explained below the list."""
    screen.erase()
    height, width = screen.getmaxyx()
    def put(row, value, attr=0):
        if 0 <= row < height and width > 1:
            try:
                screen.addnstr(row, 0, _text(value), width - 1, attr)
            except curses.error:
                pass
    put(0, title, curses.A_BOLD)
    put(1, subtitle)
    put(2, hint, curses.A_DIM)
    # Section headings get a quiet divider and breathing room. They remain
    # non-interactive and arrow navigation skips them.
    display = []
    selected_row = 0
    for index, (key, label, description) in enumerate(items):
        heading = key is None and label.isupper()
        if heading:
            if display:
                display.append(('', 0))
            label = '── ' + label + ' ' + '─' * max(0, min(width - len(label) - 5, 36))
        if index == cursor:
            selected_row = len(display)
        display.append((('  ' if key is None else '> ' if index == cursor else '  ') + label,
                        curses.A_REVERSE if index == cursor else curses.A_BOLD if heading else 0))
    visible = max(1, height - 8)
    start = max(0, selected_row - visible + 1)
    for row, (label, attr) in enumerate(display[start:start + visible]):
        put(4 + row, label, attr)
    if items:
        put(height - 3, items[cursor][2])
    put(height - 2, message)
    put(height - 1, footer or 'Draft only. Save changes creates worktrees and writes configuration; sync is separate.')
    screen.refresh()


def move(items, cursor, delta):
    candidate = cursor + delta
    while 0 <= candidate < len(items):
        if items[candidate][0] is not None:
            return candidate
        candidate += delta
    return cursor


def choose(screen, title, items, subtitle='', *, folders=False):
    cursor = next((i for i, row in enumerate(items) if row[0] is not None), 0)
    while True:
        frame(screen, title, subtitle, items, cursor)
        key = screen.getch()
        if key in (27, ord('q')):
            return None
        if folders and key == curses.KEY_LEFT:
            return 'up'
        if folders and key == curses.KEY_RIGHT:
            if isinstance(items[cursor][0], Path):
                return items[cursor][0]
            continue
        if key in (curses.KEY_DOWN, ord('j')):
            cursor = move(items, cursor, 1)
        elif key in (curses.KEY_UP, ord('k')):
            cursor = move(items, cursor, -1)
        elif key in (10, 13, curses.KEY_ENTER):
            return items[cursor][0]


def browse_folder(screen, current):
    current = current.expanduser().resolve()
    while True:
        try:
            children = sorted((p for p in current.iterdir() if p.is_dir() and not p.name.startswith('.')), key=lambda p: p.name.lower())
            message = ''
        except OSError as error:
            children = []
            message = str(error)
        items = [('select', 'Use this folder', 'Select ' + str(current)),
                 ('up', '.. Parent folder', 'Open ' + str(current.parent))]
        items += [(p, p.name + '/', 'Open this folder') for p in children]
        items.append(('cancel', 'Back without changing folder', 'Keep your previous choice.'))
        action = choose(screen, 'Orcan / Choose folder', items, str(current) + (' — ' + message if message else '') + ' | Left: parent / Right: open', folders=True)
        if action in (None, 'cancel'):
            return None
        if action == 'select':
            return current
        current = current.parent if action == 'up' else action


def pick_projects(screen, parent, connected):
    parent = parent.expanduser().resolve()
    positions = {}
    selected = []
    cursor = 2
    message = 'Open a folder with Enter; mark projects with Space, then choose Add selected projects.'
    while True:
        try:
            entries = [(path, git) for path, git in scan_dirs(parent, max_depth=1) if path != parent]
        except (OSError, ValueError, SystemExit) as error:
            entries = []
            message = str(error)
        items = [(None, 'FOLDERS', 'Browse first, then mark the directories you want to add.'),
                 ('up', '.. Return to parent folder', 'Enter or Left: open ' + str(parent.parent))]
        for path, git in entries:
            already = str(path.resolve()) in connected
            mark = 'connected' if already else 'x' if path in selected else ' '
            items.append((path, f'[{mark}] {path.name}/' + (' (Git repository)' if git else ''),
                          ('Already in this workspace. ' if already else 'Space: unselect. ' if path in selected else 'Space: select as a project. ') + 'Enter / Right: open folder. ' + str(path)))
        items.append((None, 'SELECTED PROJECTS', 'Selections are kept when you change folders.'))
        items.extend((None, '  ' + str(path), 'Selected project') for path in selected)
        if not selected:
            items.append((None, 'Nothing selected yet — use Space on a folder above.', ''))
        items += [
            (None, 'NEXT STEP', 'Return selected projects to the workspace draft; no directories are created here.'),
            ('add', f'Add selected projects ({len(selected)})', 'Add to the draft as mount as-is. Edit each project to choose its own worktree and branch.'),
            ('current', 'Select this folder as a project', str(parent)),
            ('browse', 'Jump to another folder...', 'Browse folders; selections from previous folders are kept.'),
            ('clear', 'Clear selection', 'Unselect all pending projects.'),
            ('cancel', 'Back without adding', 'Discard this selection; keep the workspace draft.'),
        ]
        cursor = max(1, min(cursor, len(items) - 1))
        if items[cursor][0] is None:
            cursor = move(items, cursor, 1)
        frame(screen, 'Orcan / Add projects', f'{len(selected)} selected | Folder: {parent}', items, cursor, message,
              hint='Enter / Right: open folder   Space: mark project   Left: parent   Up/Down: move',
              footer='Selections survive folder changes. Add selected projects returns to the draft; nothing is saved yet.')
        key = screen.getch()
        if key in (27, ord('q')):
            return []
        item = items[cursor][0]
        if key == curses.KEY_LEFT or (key in (10, 13, curses.KEY_ENTER) and item == 'up'):
            positions[parent] = cursor
            parent = parent.parent
            cursor = positions.get(parent, 2)
            message = 'Returned to parent folder. Your selections are kept.'
            continue
        if key == curses.KEY_RIGHT or (key in (10, 13, curses.KEY_ENTER) and isinstance(item, Path)):
            if isinstance(item, Path):
                positions[parent] = cursor
                parent = item
                cursor = positions.get(parent, 2)
                message = 'Opened ' + parent.name + '. Space marks a child; Select this folder adds the current directory.'
            else:
                message = 'Choose a directory row to open it.'
            continue
        if key in (curses.KEY_DOWN, ord('j')):
            cursor = move(items, cursor, 1)
        elif key in (curses.KEY_UP, ord('k')):
            cursor = move(items, cursor, -1)
        elif key in (10, 13, curses.KEY_ENTER, ord(' ')):
            if isinstance(item, Path):
                if str(item.resolve()) in connected:
                    message = 'Already connected to this workspace: ' + item.name
                elif item in selected:
                    selected.remove(item)
                    message = 'Unselected ' + item.name + '. Other selections are kept.'
                else:
                    selected.append(item)
                    message = 'Selected ' + item.name + '. Keep browsing or choose Add selected projects below.'
            elif item == 'add':
                if selected:
                    return selected
                message = 'Nothing to add yet. Use Space to mark a project folder.'
            elif item == 'browse':
                folder = browse_folder(screen, parent)
                if folder:
                    positions[parent] = cursor
                    parent = folder
                    cursor = positions.get(parent, 2)
                    message = 'Folder changed. Your selections are kept.'
            elif item == 'current':
                if str(parent.resolve()) in connected:
                    message = 'This folder is already connected to the workspace.'
                elif parent in selected:
                    message = 'This folder is already selected.'
                else:
                    selected.append(parent)
                    message = 'Selected current folder: ' + parent.name
            elif item == 'clear':
                selected.clear()
                message = 'Selection cleared. No workspace projects have been removed.'
            elif item == 'cancel':
                return []


def edit_project(screen, draft, ws, project):
    from context_tui import _prompt_line, _confirm_line
    message = ''
    while True:
        pending = '_mode' in project
        managed = is_under_managed_root(Path(project['path']))
        mode = project.get('_mode', 'worktree' if managed else 'mount')
        items = [('name', 'Name: ' + project['name'], 'The project name shown inside this workspace.')]
        if pending:
            items += [
                ('mount', ('[x]' if mode == 'mount' else '[ ]') + ' Mount as-is', 'Work directly in the existing directory. No copy is created.'),
                ('worktree', ('[x]' if mode == 'worktree' else '[ ]') + ' Worktree', 'Create a separate Git working directory on the branch below. Only this project changes.'),
            ]
            if mode == 'worktree':
                items.append(('branch', 'Branch: ' + (project['_branch'] or '(required)'), 'A separate branch for this project; other projects keep their own choices.'))
        else:
            items.append((None, 'Mode: ' + ('existing managed worktree' if managed else 'mount as-is'), 'Existing checkout stays in place. To choose a new worktree, add its source repository as a new project.'))
        items += [('path', 'Directory: ' + project['path'], 'Choose another source directory for this project.'),
                  ('remove', 'Remove project...', 'Remove from this workspace; existing directories are kept unless you explicitly select managed worktree removal.'),
                  ('back', 'Done — return to workspace', 'Keep edits in memory. Nothing is created yet.')]
        action = choose(screen, 'Orcan / Project: ' + project['name'], items, message or ws['name'])
        message = ''
        if action in (None, 'back'):
            return
        try:
            if action == 'name':
                value = _prompt_line(screen, 'Project name', project['name'])
                if value:
                    project['name'] = draft.name(value, [p['name'] for p in ws['projects'] if p is not project])
            elif action in ('mount', 'worktree'):
                if action == 'worktree' and not is_git_repo(Path(project['path'])):
                    raise ValueError('Only Git repositories support worktrees. Use mount as-is for this directory.')
                project['_mode'] = action
                if action == 'worktree' and not project['_branch']:
                    value = _prompt_line(screen, 'Branch for this project', 'feature/' + ws['name'])
                    if value:
                        project['_branch'] = value.strip()
            elif action == 'branch':
                value = _prompt_line(screen, 'Branch for this project', project['_branch'])
                if value:
                    project['_branch'] = value.strip()
            elif action == 'path':
                value = browse_folder(screen, Path(project['path']))
                if value:
                    project['path'] = str(value.resolve())
            elif action == 'remove':
                if not _confirm_line(screen, 'Remove project from this workspace?'):
                    continue
                delete = managed and _confirm_line(screen, 'Also remove its managed worktree directory on save?')
                draft.remove_project(ws, project, delete)
                return
        except (ValueError, OSError) as error:
            message = str(error)


def editor_rows(draft, ws=None):
    if ws is None:
        items = [(None, 'WORKSPACES', 'Choose a workspace to edit its name and projects.')]
        items += [(('workspace', index), w['name'] + f' ({len(w["projects"])} projects)', 'Open this workspace; all edits remain in memory.') for index, w in enumerate(draft.workspaces)]
        items += [('new', '+ Create workspace', 'Enter a name. The empty workspace appears in this draft before you add projects.')]
    else:
        items = [(None, 'WORKSPACE', 'Workspace settings'),
                 ('name', 'Name: ' + ws['name'], 'Rename this workspace in the draft.'),
                 (None, 'PROJECTS', 'Each project has its own mode and branch. Select one to edit it.')]
        for index, p in enumerate(ws['projects']):
            mode = p.get('_mode', 'worktree' if is_under_managed_root(Path(p['path'])) else 'mount')
            label = 'Worktree' if mode == 'worktree' else 'Mount as-is'
            if '_mode' in p and mode == 'worktree':
                label += ' / ' + (p['_branch'] or 'branch required')
            items.append((('project', index), p['name'] + ' — ' + label, 'Edit name, mode and branch for this project. Directory: ' + p['path']))
        items += [('add', '+ Add projects', 'Select one or several directories, then edit their modes individually.'),
                  ('delete', 'Remove workspace...', 'Remove this workspace and all its project entries. Choose separately whether to remove managed worktree directories.')]
    count = sum(p.get('_mode') == 'worktree' for w in draft.workspaces for p in w['projects'])
    items += [(None, 'SUMMARY — ALL WORKSPACES', 'Nothing is written until Save changes.'),
              (None, f'{len(draft.workspaces)} workspaces / {count} new worktrees / {len(draft.removals)} directory removals', 'Mount as-is directories are kept. Existing configuration settings are preserved.'),
              ('save', 'Save changes', 'Validate the full draft, create worktrees and write configuration. Does not run sync.'),
              ('back' if ws else 'discard', 'Back to workspace list' if ws else 'Close / discard draft', 'Keep editing other workspaces.' if ws else 'Leave without saving; confirm if the draft has changes.')]
    return items


def run(screen, draft, args):
    from context_tui import _init_curses_session, _prompt_line, _confirm_line
    _init_curses_session()
    curses.curs_set(0)
    screen.keypad(True)
    ws = None
    if args.workspace:
        ws = next((w for w in draft.workspaces if w['name'] == args.workspace), None)
        if ws is None:
            ws = draft.add_workspace(args.workspace)
    cursor = 1
    message = ''
    while True:
        items = editor_rows(draft, ws)
        cursor = min(cursor, len(items) - 1)
        if items[cursor][0] is None:
            cursor = next(i for i, row in enumerate(items) if row[0] is not None)
        frame(screen, 'Orcan / ' + ('Workspace: ' + ws['name'] if ws else 'Workspaces'),
              'Unsaved changes' if draft.dirty else 'Configuration matches the saved draft', items, cursor, message)
        key = screen.getch()
        if key in (curses.KEY_DOWN, ord('j')):
            cursor = move(items, cursor, 1)
            continue
        if key in (curses.KEY_UP, ord('k')):
            cursor = move(items, cursor, -1)
            continue
        if key in (27, ord('q')):
            action = 'back' if ws else 'discard'
        elif key in (10, 13, curses.KEY_ENTER):
            action = items[cursor][0]
        else:
            continue
        message = ''
        try:
            if isinstance(action, tuple):
                kind, index = action
                if kind == 'workspace':
                    ws = draft.workspaces[index]
                    cursor = 1
                else:
                    edit_project(screen, draft, ws, ws['projects'][index])
            elif action == 'new':
                value = _prompt_line(screen, 'New workspace name', '')
                if value:
                    ws = draft.add_workspace(value)
                    cursor = 1
            elif action == 'name':
                value = _prompt_line(screen, 'Workspace name', ws['name'])
                if value:
                    ws['name'] = draft.name(value, [w['name'] for w in draft.workspaces if w is not ws])
            elif action == 'add':
                parent = Path(args.dir).expanduser() if args.dir else Path(ws['projects'][0]['path']).parent if ws['projects'] else Path.cwd()
                paths = pick_projects(screen, parent, {p['path'] for p in ws['projects']})
                draft.add_projects(ws, paths)
                message = 'Projects added as mount as-is. Select each project to choose its mode and branch.' if paths else ''
            elif action == 'delete':
                if _confirm_line(screen, 'Remove workspace and all its project entries?'):
                    managed = any(is_under_managed_root(Path(p['path'])) for p in ws['projects'])
                    delete = managed and _confirm_line(screen, 'Also remove its managed worktree directories on save?')
                    draft.remove_workspace(ws, delete)
                    ws = None
                    cursor = 1
            elif action == 'back':
                ws = None
                cursor = 1
            elif action == 'discard':
                if not draft.dirty or _confirm_line(screen, 'Discard unsaved changes and close?' + (' Previously created worktrees will remain on disk.' if draft.created else '')):
                    return 1
            elif action == 'save':
                if not draft.dirty:
                    message = 'No changes to save.'
                    continue
                draft.validate()
                if _confirm_line(screen, 'Save all workspace changes and perform the listed filesystem operations?'):
                    import contextlib
                    import io
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        draft.save()
                    return 0
        except (Exception, SystemExit) as error:
            message = str(error) or 'Save failed. Draft retained; review and retry.'
            if draft.created:
                message += ' Created worktrees are retained for retry; no automatic cleanup.'


def main(args, config_path):
    draft = WorkspaceDraft(config_path)
    draft.start_point = args.start_point
    return curses.wrapper(run, draft, args)
