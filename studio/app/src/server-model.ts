import type { ProbeReport } from "./types";

/** Never present an old runtime observation as a current container state. */
export function containerStateLabel(status?: { state: "checking" | "online" | "offline"; report?: ProbeReport }): string {
  if (status?.state === "checking") return "checking…";
  if (status?.state === "online") return status.report?.runtime.docker.container.state ?? "unknown";
  return status?.report ? "stale" : "not checked";
}
