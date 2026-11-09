"""In-memory workspace editing; filesystem operations happen only on save."""
from __future__ import annotations

import copy
import os
import subprocess
from pathlib import Path

from config_io import dump_config, load_config_or_create
from context_selection import NAME_RE, worktree_is_dirty
from git_worktrees import (
    BRANCH_RE, ManifestEntry, create_worktree, find_worktree_by_branch, is_git_repo,
    is_under_managed_root, load_manifest, managed_worktree_path,
    manifest_remove, manifest_upsert, remove_worktree,
)
from path_guards import checked_workspace_project


class WorkspaceDraft:
    def __init__(self, path):
        self.path = Path(path).resolve()
        snapshot = load_config_or_create(self.path)
        self.revision = snapshot.revision
        self.original = copy.deepcopy(dict(snapshot))
        self.data = copy.deepcopy(self.original)
        self.workspaces = self.data.setdefault('workspaces', [])
        if not isinstance(self.workspaces, list):
            raise ValueError('workspaces must be an array')
        self.start_point = 'HEAD'
        self.removals = []
        self.created = {}  # Keep receipts if a later save step fails; never delete them blindly.

    @property
    def dirty(self):
        return self.data != self.original or bool(self.removals)

    def name(self, value, used):
        value = value.strip()
        if not NAME_RE.fullmatch(value):
            raise ValueError('Use letters, digits, dots, underscores or hyphens for the name.')
        if value in used:
            raise ValueError(f'Name already used: {value}')
        return value

    def add_workspace(self, name):
        name = self.name(name, [ws['name'] for ws in self.workspaces])
        ws = {'name': name, 'projects': []}
        self.workspaces.append(ws)
        return ws

    def add_projects(self, ws, paths):
        # Validate the whole selection before changing the draft.
        paths = [checked_workspace_project(Path(p), Path(os.environ.get('ORCAN_HOME') or self.path.parent)) for p in paths]
        names = {p['name'] for p in ws['projects']}
        known = {p['path'] for p in ws['projects']}
        for path in paths:
            if str(path) in known:
                continue
            base = path.name
            name = base
            number = 2
            while name in names:
                name = f'{base}-{number}'
                number += 1
            self.name(name, [])
            ws['projects'].append({'name': name, 'path': str(path), '_mode': 'mount', '_branch': ''})
            names.add(name)
            known.add(str(path))

    def remove_project(self, ws, project, delete_worktree=False):
        if delete_worktree and is_under_managed_root(Path(project['path'])):
            self.removals.append(project['path'])
        ws['projects'].remove(project)

    def remove_workspace(self, ws, delete_worktrees=False):
        for project in list(ws['projects']):
            self.remove_project(ws, project, delete_worktrees)
        self.workspaces.remove(ws)

    def validate(self):
        actual = self.path.read_bytes() if self.path.exists() else b''
        if actual != self.revision:
            raise ValueError('Configuration changed in another session. Exit and reopen before saving.')
        names = set()
        targets = set()
        branches = set()
        for ws in self.workspaces:
            self.name(ws['name'], names)
            names.add(ws['name'])
            project_names = set()
            for project in ws['projects']:
                self.name(project['name'], project_names)
                project_names.add(project['name'])
                original_paths = {p['path'] for w in self.original.get('workspaces', []) for p in w.get('projects', [])}
                if '_mode' not in project:
                    if project['path'] not in original_paths:
                        checked_workspace_project(Path(project['path']), Path(os.environ.get('ORCAN_HOME') or self.path.parent))
                    continue
                repo = checked_workspace_project(Path(project['path']), Path(os.environ.get('ORCAN_HOME') or self.path.parent))
                if project['_mode'] != 'worktree':
                    continue
                if not is_git_repo(repo):
                    raise ValueError(f'Worktree requires a Git repository: {repo}')
                branch = project['_branch'].strip()
                result = subprocess.run(['git', 'check-ref-format', '--branch', branch], capture_output=True)
                if not branch or not BRANCH_RE.fullmatch(branch) or result.returncode:
                    raise ValueError(f'Invalid branch for {project["name"]}: {branch}')
                if subprocess.run(['git', '-C', str(repo), 'rev-parse', '--verify', self.start_point + '^{commit}'], capture_output=True).returncode:
                    raise ValueError(f'Invalid worktree start point for {project["name"]}: {self.start_point}')
                common = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--git-common-dir'], capture_output=True, text=True, check=True).stdout.strip()
                common_path = (repo / common).resolve()
                identity = (str(common_path), branch)
                target = managed_worktree_path(ws['name'], project['name'])
                receipt = self.created.get((str(repo), branch, str(target)))
                if identity in branches or str(target) in targets:
                    raise ValueError(f'Duplicate worktree branch or destination: {project["name"]}')
                branches.add(identity)
                targets.add(str(target))
                if not receipt and (target.exists() or find_worktree_by_branch(repo, branch)):
                    raise ValueError(f'Branch or worktree directory is already in use: {project["name"]} / {branch}. Use mount as-is for an existing checkout.')
        for path in self.removals:
            if Path(path).exists() and worktree_is_dirty(Path(path)):
                raise ValueError(f'Worktree has local changes; keep its directory or clean it first: {path}')

    def save(self):
        self.validate()
        output = copy.deepcopy(self.data)
        for ws in output['workspaces']:
            for project in ws['projects']:
                mode = project.pop('_mode', None)
                branch = project.pop('_branch', '')
                if mode == 'worktree':
                    repo = Path(project['path'])
                    target = managed_worktree_path(ws['name'], project['name'])
                    key = (str(repo), branch, str(target))
                    if key not in self.created:
                        wt = create_worktree(repo, branch=branch, start_point=self.start_point, workspace=ws['name'], project=project['name'], managed=True, fatal=False)
                        self.created[key] = str(wt.path)
                    project['path'] = self.created[key]
        dump_config(self.path, output, expected=self.revision)
        self.revision = self.path.read_bytes()
        self.data = output
        self.workspaces = self.data['workspaces']
        self.original = copy.deepcopy(output)
        # Reconcile managed registry names only after configuration is saved.
        by_path = {p['path']: (ws['name'], p['name']) for ws in self.workspaces for p in ws['projects']}
        for entry in load_manifest():
            if entry.path in by_path:
                workspace, project = by_path[entry.path]
                if (entry.workspace, entry.project) != (workspace, project):
                    manifest_remove(workspace=entry.workspace, project=entry.project)
                    manifest_upsert(ManifestEntry(workspace=workspace, project=project, repo=entry.repo, path=entry.path, branch=entry.branch))
        for path in list(self.removals):
            if path in by_path:
                self.removals.remove(path)
                continue
            if Path(path).exists():
                remove_worktree(Path(path), force=False, allow_unmanaged=False)
            for entry in load_manifest():
                if entry.path == path:
                    manifest_remove(workspace=entry.workspace, project=entry.project)
            self.removals.remove(path)
        self.created.clear()
