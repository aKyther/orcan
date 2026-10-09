import type { ProbeReport } from "./types";

export type GroupMember = { host_id: string; container_id: string; profile_id: string; instance: string | null; label: string; x: number; y: number };
export type GroupEdge = { id: string; source: string; target: string };
export type Group = { id: string; revision: number; name: string; members: GroupMember[]; edges: GroupEdge[] };
export type MemberState = { state: "unchecked" | "checking" | "ready" | "offline" | "mismatch"; report?: ProbeReport; error?: string };

export function targetMatches(report: ProbeReport, member: GroupMember): boolean {
  return report.target?.state === "ready" && report.target.host_id === member.host_id && report.target.container_id === member.container_id;
}

export function removeMember(group: Group, id: string): void {
  group.members = group.members.filter((member) => member.container_id !== id);
  group.edges = group.edges.filter((edge) => edge.source !== id && edge.target !== id);
}

export function attachAvailable(state?: MemberState): boolean {
  return state?.state === "ready" && state.report?.runtime.docker.container.state === "running" && Boolean(state.report.context.workspaces.length);
}
