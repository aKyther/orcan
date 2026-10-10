import type { ProbeReport } from "./types";

export type ServerCapacity = { cpus?: number; memoryBytes?: number; diskTotalBytes?: number; diskFreeBytes?: number; diskPath?: string };

/** Never present an old runtime observation as a current container state. */
export function containerStateLabel(status?: { state: "checking" | "online" | "offline"; report?: ProbeReport }): string {
  if (status?.state === "checking") return "checking…";
  if (status?.state === "online") return status.report?.runtime.docker.container.state ?? "unknown";
  return status?.report ? "stale" : "not checked";
}

const SELECTION_KEY = "orcan-studio:selected-containers";
export function loadContainerSelections(): Map<string, string> {
  try {
    const raw = JSON.parse(localStorage.getItem(SELECTION_KEY) ?? "{}");
    return new Map(Object.entries(raw && typeof raw === "object" ? raw : {}).filter((entry): entry is [string, string] => typeof entry[1] === "string" && (entry[1] === "" || /^[a-z][a-z0-9-]{0,47}$/.test(entry[1]))));
  } catch { return new Map(); }
}
export function persistContainerSelections(selections: Map<string, string>): void {
  try { localStorage.setItem(SELECTION_KEY, JSON.stringify(Object.fromEntries(selections))); } catch { /* Device preference only. */ }
}
