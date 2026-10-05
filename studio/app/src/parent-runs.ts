export type ParentRun = { path: string; branch: string; at: string };

const STORAGE_KEY = "orcan-studio:parent-runs";

export function loadParentRuns(): ParentRun[] {
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(saved)
      ? saved.filter((item): item is ParentRun => Boolean(item) && typeof item === "object" && typeof (item as ParentRun).path === "string" && typeof (item as ParentRun).branch === "string" && typeof (item as ParentRun).at === "string")
      : [];
  } catch {
    return [];
  }
}

export function rememberParentRun(runs: ParentRun[], path: string, branch: string): void {
  const existing = runs.findIndex((run) => run.path === path && run.branch === branch);
  if (existing >= 0) runs.splice(existing, 1);
  runs.unshift({ path, branch, at: new Date().toISOString() });
  runs.splice(20);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(runs));
  } catch {
    // Browser storage is an enhancement only.
  }
}
