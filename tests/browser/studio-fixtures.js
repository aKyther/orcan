/** Synthetic host data only; never reads a developer snapshot or credentials. */
function largeReport() {
  const root = '/fixture/sandbox';
  const trees = '/fixture/worktrees';
  const projects = Array.from({ length: 100 }, (_, index) => ({
    name: `project-${String(index).padStart(3, '0')}`,
    path: `${index % 7 === 0 ? trees : root}/team-${Math.floor(index / 20)}/project-${String(index).padStart(3, '0')}`,
    kind: index % 5 === 0 ? 'directory' : index % 7 === 0 ? 'git_worktree' : 'git_repository',
    repository_id: index % 5 === 0 ? undefined : `repo-${index}`,
    branch: index % 5 === 0 ? undefined : 'main',
    dirty: index % 5 === 0 ? undefined : index % 9 === 0,
    writable: true,
  }));
  const workspaces = Array.from({ length: 10 }, (_, index) => ({
    name: `work-${String(index).padStart(2, '0')}`,
    projects: [...projects.slice(index * 10, index * 10 + 10), ...(index ? [projects[1]] : [])],
  }));
  return {
    sandbox: { version: 'fixture' },
    host: { os: 'Linux', architecture: 'x86_64' },
    capabilities: { docker: true, managed_projects: true, live_reconcile: true },
    runtime: { docker: { available: true, image: { name: 'orcan:fixture', present: true }, container: { name: 'orcan-1', state: 'running' }, agents: { codex: true } } },
    paths: { home: '/fixture', data: '/fixture', projects_root: root, workspace_metadata_root: '/fixture/workspaces', managed_worktrees_root: trees },
    context: {
      workspaces, managed_projects: projects,
      repositories: projects.filter(project => project.repository_id).map(project => ({
        repository_id: project.repository_id,
        bindings: workspaces.filter(workspace => workspace.projects.some(item => item.path === project.path)).map(workspace => ({ workspace: workspace.name })),
      })),
      update_targets: projects.filter(project => project.kind === 'git_repository').map(project => ({
        ...project, role: 'configured_mount', worktree_count: 0, read_only: true, eligible: !project.dirty, upstream: 'origin/main', ahead: 0, behind: 0,
      })),
      configuration: { state: 'present', source: 'config', editable: true, path: '/fixture/orcan.config.json', revision: 'fixture' },
    },
  };
}

module.exports = { largeReport };
