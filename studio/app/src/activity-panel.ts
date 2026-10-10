import { actionButton, el } from "./dom";
import { loadJobs, persistJobs, type Job } from "./activity";
import type { Connection, ConnectionProfile } from "./types";

type Options = {
  container: HTMLElement; current: () => Connection | undefined;
  profiles: () => ConnectionProfile[];
  open: (profile: ConnectionProfile) => unknown;
  retry: (profile: ConnectionProfile) => unknown;
};

/** The activity view owns its filter, rendering and bounded history. */
export function activityPanel(options: Options) {
  const jobsList = options.container;
  const activityFilter = document.createElement("select");
  activityFilter.className = "activity-filter";
  activityFilter.setAttribute("aria-label", "Filter activity by container");
  jobsList.before(activityFilter);
  const jobs = loadJobs();
  function saveJobs(): void { persistJobs(jobs); }
  function addJob(name: string, detail: string, enclave = options.current()?.label, profileId = options.current()?.profileId): Job { const job = { name, detail, enclave, profileId, state: "running" as const, at: new Date().toISOString() }; jobs.unshift(job); jobs.splice(50); saveJobs(); renderJobs(); return job; }
  function finishJob(job: Job, state: "succeeded" | "failed", detail: string): void { job.state = state; job.detail = detail; saveJobs(); renderJobs(); }
  function renderJobs(): void {
    const selected = activityFilter.value;
    const enclaves = [...new Set(jobs.map((job) => job.enclave ?? "Other"))];
    activityFilter.replaceChildren(new Option("All Servers", ""), ...enclaves.map((enclave) => new Option(enclave, enclave)));
    activityFilter.value = enclaves.includes(selected) ? selected : "";
    const visible = selected ? jobs.filter((job) => (job.enclave ?? "Other") === selected) : jobs;
    jobsList.replaceChildren(...(visible.length ? visible.map((job) => {
      const row = document.createElement("div");
      row.className = `job ${job.state}`;
      const profile = options.profiles().find((item) => item.id === job.profileId) ?? options.profiles().find((item) => item.name === job.enclave);
      const actions: HTMLElement[] = [];
      if (profile) actions.push(actionButton("Open", () => void options.open(profile), "secondary"));
      if (job.state === "failed" && profile) actions.push(actionButton("Retry check", () => void options.retry(profile), "secondary"));
      row.append(el("span", { textContent: `${new Date(job.at).toLocaleString()} · ${job.enclave ?? "Other"} · ${job.name} · ${job.state} · ${job.detail}` }), ...actions);
      return row;
    }) : [Object.assign(document.createElement("p"), { className: "snapshot-shared", textContent: "No activity for this container." })]));
  }
  activityFilter.addEventListener("change", renderJobs);

  return { addJob, finishJob, renderJobs };
}

