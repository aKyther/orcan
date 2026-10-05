export type MapFilter = "attention" | "git" | "worktree" | "mount" | "unassigned" | "dirty" | "planned" | "orphan";
type SavedMapState = { filters?: MapFilter[]; workspace?: string };

const STORAGE_KEY = "orcan-studio:map-state";
const filters = new Set<MapFilter>(["attention", "git", "worktree", "mount", "unassigned", "dirty", "planned", "orphan"]);

function isMapFilter(value: unknown): value is MapFilter {
  return typeof value === "string" && filters.has(value as MapFilter);
}

export function loadMapState(key: string): SavedMapState | undefined {
  try {
    const all: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
    if (!all || typeof all !== "object") return undefined;
    const saved = (all as Record<string, unknown>)[key];
    if (!saved || typeof saved !== "object") return undefined;
    const value = saved as Record<string, unknown>;
    return {
      filters: Array.isArray(value.filters) ? value.filters.filter(isMapFilter) : undefined,
      workspace: typeof value.workspace === "string" ? value.workspace : undefined,
    };
  } catch {
    return undefined;
  }
}

export function persistMapState(key: string, state: SavedMapState): void {
  try {
    const raw: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
    const all = raw && typeof raw === "object" ? raw as Record<string, unknown> : {};
    all[key] = state;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
  } catch {
    // Browser storage is an enhancement only.
  }
}
