import type { ParentRun } from "./parent-runs";
import type { ProbeReport, ProjectRef } from "./types";

export type ParentCandidate = {
  path: string; name: string; role: "worktree_parent" | "configured_mount"; worktree_count: number;
  readOnly: boolean; eligible: boolean; repositoryId?: string; branch?: string; dirty?: boolean;
  upstream?: string; ahead?: number; behind?: number;
};
export type ContextProject = ProbeReport["context"]["workspaces"][number]["projects"][number];
export type HealthProject = { path: string; kind?: string; writable?: boolean; dirty?: boolean; repository_id?: string };

export function parentCandidates(report: ProbeReport, runs: ParentRun[]): ParentCandidate[] {
  return report.context.update_targets.map((target) => ({
    path: target.path, name: target.name, role: target.role,
    worktree_count: target.worktree_count, readOnly: target.read_only,
    eligible: target.eligible, repositoryId: target.repository_id, branch: target.branch, dirty: target.dirty,
    upstream: target.upstream, ahead: target.ahead, behind: target.behind,
  })).sort((left, right) => {
    if (left.role !== right.role) return left.role === "worktree_parent" ? -1 : 1;
    const leftRun = runs.find((run) => run.path === left.path)?.at ?? "";
    const rightRun = runs.find((run) => run.path === right.path)?.at ?? "";
    return rightRun.localeCompare(leftRun) || left.name.localeCompare(right.name);
  });
}

export function parentForProject(report: ProbeReport, project: ContextProject, runs: ParentRun[]): ParentCandidate | undefined {
  const candidates = parentCandidates(report, runs);
  return candidates.find((candidate) => candidate.repositoryId && candidate.repositoryId === project.repository_id)
    ?? candidates.find((candidate) => candidate.path === project.path);
}

export function projectName(project: { name?: string; path: string }): string {
  return project.name ?? project.path.split("/").pop() ?? project.path;
}

export function unassignedProjects(report: ProbeReport): Array<{ path: string; kind: string }> {
  const used = new Set(report.context.workspaces.flatMap((workspace) => workspace.projects.map((project) => project.path)));
  return report.context.managed_projects.filter((project) => !used.has(project.path));
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

export function projectAlerts(report: ProbeReport, project: HealthProject, orphan = false): string[] {
  const alerts: string[] = [];
  if (project.kind === "missing") alerts.push("missing");
  else if (project.writable === false) alerts.push("read-only");
  if (project.dirty) alerts.push("uncommitted");
  if (orphan) alerts.push("orphan worktree");
  const source = project.repository_id
    ? report.context.update_targets.find((target) => target.repository_id === project.repository_id)
    : undefined;
  if (source?.behind) alerts.push(`source ${source.behind} behind`);
  return alerts;
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
