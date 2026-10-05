export type Job = { name: string; state: "running" | "succeeded" | "failed"; detail: string; at: string; enclave?: string; profileId?: string };

const STORAGE_KEY = "orcan-studio:jobs";

function isJob(value: unknown): value is Job {
  if (!value || typeof value !== "object") return false;
  const job = value as Partial<Job>;
  return typeof job.name === "string" && typeof job.detail === "string" && typeof job.at === "string"
    && (job.state === "running" || job.state === "succeeded" || job.state === "failed")
    && (job.enclave === undefined || typeof job.enclave === "string")
    && (job.profileId === undefined || typeof job.profileId === "string");
}

export function loadJobs(): Job[] {
  try {
    const stored: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(stored) ? stored.filter(isJob).slice(0, 50) : [];
  } catch {
    return [];
  }
}

export function persistJobs(jobs: Job[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(jobs.slice(0, 50)));
  } catch {
    // Browser storage is an enhancement only.
  }
}
