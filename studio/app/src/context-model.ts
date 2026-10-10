import type { ParentRun } from "./parent-runs";
import type { ProbeReport, ProjectRef } from "./types";

export type ParentCandidate = {
  path: string; name: string; role: "worktree_parent" | "configured_mount"; worktree_count: number;
  readOnly: boolean; eligible: boolean; repositoryId?: string; branch?: string; dirty?: boolean | null;
  upstream?: string; ahead?: number; behind?: number;
};
export type ContextProject = ProbeReport["context"]["workspaces"][number]["projects"][number];
export type HealthProject = { path: string; kind?: string; writable?: boolean; dirty?: boolean | null; repository_id?: string };

export function validateBranches(value: unknown): string[] {
  if (!Array.isArray(value) || !value.every((branch) => typeof branch === "string")) {
    throw new Error("Orcan did not return a valid branch list. Update the host CLI and reconnect.");
  }
  return value;
}

export function parentCandidates(report: ProbeReport, runs: ParentRun[]): ParentCandidate[] {
  const runsByPath = new Map(runs.map((run) => [run.path, run.at]));
  return report.context.update_targets.map((target) => ({
    path: target.path, name: target.name, role: target.role,
    worktree_count: target.worktree_count, readOnly: target.read_only,
    eligible: target.eligible, repositoryId: target.repository_id, branch: target.branch, dirty: target.dirty,
    upstream: target.upstream, ahead: target.ahead, behind: target.behind,
  })).sort((left, right) => {
    if (left.role !== right.role) return left.role === "worktree_parent" ? -1 : 1;
    const leftRun = runsByPath.get(left.path) ?? "";
    const rightRun = runsByPath.get(right.path) ?? "";
    return rightRun.localeCompare(leftRun) || left.name.localeCompare(right.name);
  });
}

/** Build once per render, never retain across a refreshed report/history. */
export function indexParents(report: ProbeReport, runs: ParentRun[]) {
  const candidates = parentCandidates(report, runs);
  const byPath = new Map<string, ParentCandidate>();
  const byRepository = new Map<string, ParentCandidate>();
  for (const candidate of candidates) {
    if (!byPath.has(candidate.path)) byPath.set(candidate.path, candidate);
    if (candidate.repositoryId && !byRepository.has(candidate.repositoryId)) byRepository.set(candidate.repositoryId, candidate);
  }
  return { candidates, forProject: (project: ContextProject) =>
    (project.repository_id ? byRepository.get(project.repository_id) : undefined) ?? byPath.get(project.path) };
}

export function projectName(project: { name?: string; path: string }): string {
  return project.name ?? project.path.split("/").pop() ?? project.path;
}

export function parseDraggedProject(value: string): ProjectRef | undefined {
  try {
    const project: unknown = JSON.parse(value);
    if (!project || typeof project !== "object") return undefined;
    const candidate = project as Partial<ProjectRef>;
    return typeof candidate.name === "string" && typeof candidate.path === "string"
      ? { name: candidate.name, path: candidate.path, kind: typeof candidate.kind === "string" ? candidate.kind : undefined }
      : undefined;
  } catch {
    return undefined;
  }
}

export function projectAlerts(report: ProbeReport, project: HealthProject, orphan = false, sources?: ReadonlyMap<string, ProbeReport["context"]["update_targets"][number]>): string[] {
  const alerts: string[] = [];
  if (project.kind === "missing") alerts.push("missing");
  else if (project.writable === false) alerts.push("read-only");
  if (project.dirty) alerts.push("uncommitted");
  else if (project.dirty === null) alerts.push("Git status unknown");
  if (orphan) alerts.push("orphan worktree");
  const source = project.repository_id
    ? sources ? sources.get(project.repository_id) : report.context.update_targets.find((target) => target.repository_id === project.repository_id)
    : undefined;
  if (source?.behind) alerts.push(`source ${source.behind} behind`);
  return alerts;
}

/** One ephemeral index per map render, never a cache of host authority. */
export function indexContext(report: ProbeReport) {
  const sources = new Map<string, ProbeReport["context"]["update_targets"][number]>();
  const workspacesByPath = new Map<string, Set<string>>();
  const dirtyByPath = new Map<string, boolean | null | undefined>();
  for (const source of report.context.update_targets) {
    if (source.repository_id && !sources.has(source.repository_id)) sources.set(source.repository_id, source);
    dirtyByPath.set(source.path, source.dirty);
  }
  for (const workspace of report.context.workspaces) {
    for (const project of workspace.projects) {
      const names = workspacesByPath.get(project.path) ?? new Set<string>();
      names.add(workspace.name);
      workspacesByPath.set(project.path, names);
      const previous = dirtyByPath.get(project.path);
      dirtyByPath.set(project.path, previous === true || project.dirty === true ? true
        : previous === null || project.dirty === null ? null : project.dirty ?? previous);
    }
  }
  return {
    used: new Set(workspacesByPath.keys()), workspacesByPath,
    health: <T extends HealthProject>(project: T): T => dirtyByPath.has(project.path) ? { ...project, dirty: dirtyByPath.get(project.path) } : project,
    alerts: (project: HealthProject, orphan = false) => projectAlerts(report, project, orphan, sources),
  };
}

export function parentDirectory(path: string): string {
  const separator = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  return separator > 0 ? path.slice(0, separator) : path;
}

export function parentLabel(path: string): string {
  return path.slice(Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\")) + 1) || path;
}

export function projectGroup(report: ProbeReport, path: string): string | undefined {
  const parent = parentDirectory(path);
  return parent === report.paths.projects_root ? undefined : parent;
}
