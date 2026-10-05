import type { ProjectRef } from "./types";

export type QueuedChange = {
  id: string;
  enclave: string;
  action: "attach" | "detach";
  workspace: string;
  project: ProjectRef;
  projectMode: "git" | "mount";
  relationship: "share" | "worktree";
  branch?: string;
  changes: string[];
  error?: string;
};

const STORAGE_KEY = "orcan-studio:context-drafts";

function isQueuedChange(value: unknown): value is QueuedChange {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<QueuedChange>;
  return typeof item.id === "string" && typeof item.enclave === "string"
    && (item.action === "attach" || item.action === "detach")
    && typeof item.workspace === "string" && typeof item.project?.path === "string"
    && typeof item.project?.name === "string" && (item.projectMode === "git" || item.projectMode === "mount")
    && (item.relationship === "share" || item.relationship === "worktree")
    && Array.isArray(item.changes) && item.changes.every((change) => typeof change === "string")
    && (item.branch === undefined || typeof item.branch === "string")
    && (item.error === undefined || typeof item.error === "string");
}

export function loadQueuedChanges(): QueuedChange[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(value) ? value.filter(isQueuedChange) : [];
  } catch {
    return [];
  }
}

export function persistQueuedChanges(changes: QueuedChange[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(changes));
  } catch {
    // Browser storage is an enhancement only.
  }
}

export function draftConflicts(changes: QueuedChange[]): Map<string, string> {
  const conflicts = new Map<string, string>();
  const relationships = new Map<string, QueuedChange[]>();
  const worktrees = new Map<string, QueuedChange[]>();
  for (const change of changes) {
    const relationship = `${change.workspace}\u0000${change.project.path}`;
    (relationships.get(relationship) ?? relationships.set(relationship, []).get(relationship)!).push(change);
    if (change.action === "attach" && change.relationship === "worktree" && change.branch) {
      const worktree = `${change.project.path}\u0000${change.branch}`;
      (worktrees.get(worktree) ?? worktrees.set(worktree, []).get(worktree)!).push(change);
    }
  }
  for (const entries of relationships.values()) {
    if (new Set(entries.map((change) => change.action)).size > 1) {
      for (const change of entries) conflicts.set(change.id, "Conflicts with an attach/detach draft for the same workspace and project or folder.");
    }
  }
  for (const entries of worktrees.values()) {
    if (entries.length > 1) {
      for (const change of entries) conflicts.set(change.id, "Another draft creates a worktree from this repository with the same branch.");
    }
  }
  return conflicts;
}
