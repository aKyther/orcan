export type WorktreeResult = {
  outcome?: "complete" | "partial";
  result: { path: string; completed?: string[]; pending_workspaces?: string[]; error?: string; retry?: string };
};

export function worktreeSummary(response: WorktreeResult): string {
  if (response.outcome !== "partial") return `Created: ${response.result.path}`;
  return `${(response.result.completed ?? []).join(" · ")}. Remaining: ${(response.result.pending_workspaces ?? []).join(", ")}. ${response.result.error ?? "Attachment failed"}. Worktree preserved: ${response.result.path}`;
}

export async function retryAttachments(response: WorktreeResult, attach: (workspace: string, path: string) => Promise<unknown>): Promise<void> {
  if (response.outcome !== "partial" || response.result.retry !== "attachments_only") throw new Error("Refresh the host before retrying.");
  const pending = response.result.pending_workspaces ?? [];
  while (pending.length) {
    await attach(pending[0], response.result.path);
    pending.shift();
  }
  response.outcome = "complete";
}
