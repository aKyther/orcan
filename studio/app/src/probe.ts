import type { ProbeReport } from "./types";

/** Keep older preview snapshots useful when newly-added collections are null. */
export function normalizeProbeReport(report: ProbeReport): ProbeReport {
  const context = report.context;
  return {
    ...report,
    context: {
      ...context,
      workspaces: Array.isArray(context.workspaces) ? context.workspaces : [],
      managed_projects: Array.isArray(context.managed_projects) ? context.managed_projects : [],
      repositories: Array.isArray(context.repositories) ? context.repositories : [],
      update_targets: Array.isArray(context.update_targets) ? context.update_targets : [],
    },
  };
}
