import type { ProbeReport } from "./types";

export function loadCachedReport(key: string): ProbeReport | undefined {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) as ProbeReport : undefined;
  } catch {
    return undefined;
  }
}

export function persistCachedReport(key: string, report: ProbeReport): void {
  try {
    localStorage.setItem(key, JSON.stringify(report));
  } catch {
    // Browser storage is an enhancement only.
  }
}
