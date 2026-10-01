import { invoke as tauriInvoke } from "@tauri-apps/api/core";
import "./style.css";

type Target =
  | { kind: "local" }
  | { kind: "wsl2"; distribution: string }
  | { kind: "ssh"; destination: string };

type ProbeReport = {
  sandbox: { version: string };
  host: { os: string; architecture: string };
  capabilities: { docker: boolean; managed_projects: boolean; live_reconcile: boolean };
  runtime: {
    docker: { container: { state: string }; agents?: Record<string, boolean> };
    resources?: { cpus?: string | number; memory?: string; shm_size?: string; tmpfs_size?: string };
    launch?: { recorded: boolean; docker?: boolean; git?: boolean; network?: string | null; ttyd?: boolean; ttyd_auth?: boolean };
  };
  paths: { home: string; data: string; projects_root: string; workspace_metadata_root: string; managed_worktrees_root: string };
  context: {
    workspaces: Array<{
      name: string;
      projects: Array<{ name?: string; path: string; kind: string; writable?: boolean; branch?: string; dirty?: boolean; upstream?: string; ahead?: number; behind?: number; repository_id?: string }>;
    }>;
    managed_projects: Array<{ path: string; kind: string; writable?: boolean; repository_id?: string; branch?: string; dirty?: boolean; upstream?: string; ahead?: number; behind?: number; origin_url?: string }>;
    repositories: Array<{ repository_id: string; origin_url?: string; bindings: Array<{ workspace: string }> }>;
    update_targets: Array<{ name: string; path: string; kind: string; role: "worktree_parent" | "configured_mount"; worktree_count: number; read_only: boolean; eligible: boolean; repository_id?: string; branch?: string; dirty?: boolean; upstream?: string; ahead?: number; behind?: number }>;
    configuration: { state: string; revision?: string; source?: "config" | "runtime_index" | "none"; editable?: boolean };
  };
};

type SshAuthentication =
  | { kind: "agent" }
  | { kind: "password" }
  | { kind: "private_key"; path: string; has_passphrase: boolean };
type SshOptions = { username?: string; authentication: SshAuthentication };
type ConnectionProfile = { id: string; name: string; target: Target; ssh?: SshOptions; credential_id?: string };
type Credential = { id: string; name: string; authentication: SshAuthentication };
/** The Enclave Studio is talking to; set before every probe. */
type Connection = { target: Target; label: string; profileId?: string; credentialId?: string; username?: string };

const result = document.querySelector<HTMLOutputElement>("#result")!;
const $ = <T extends HTMLElement>(selector: string) => document.querySelector<T>(selector)!;
const profileList = $("#profile-list");
const enclaveList = $("#enclave-list");
const credentialList = $("#credential-list");
const setupPanel = $("#setup-panel");
const activeGroup = $("#active-group");
const profileFormTitle = $("#profile-form-title");
const profileName = $<HTMLInputElement>("#profile-name");
const wslFields = $("#wsl-fields");
const wslDistribution = $<HTMLInputElement>("#wsl-distribution");
const sshFields = $("#ssh-fields");
const sshHost = $<HTMLInputElement>("#ssh-host");
const sshUser = $<HTMLInputElement>("#ssh-user");
const credentialSelect = $<HTMLSelectElement>("#credential-select");
const credentialHint = $("#credential-hint");
const profileTestResult = $<HTMLOutputElement>("#profile-test-result");
const profileTestHint = $("#profile-test-hint");
const profileDelete = $<HTMLButtonElement>("#profile-delete");
const profileTest = $<HTMLButtonElement>("#profile-test");
const profileSave = $<HTMLButtonElement>("#profile-save");
const credentialFormTitle = $("#credential-form-title");
const credentialName = $<HTMLInputElement>("#credential-name");
const keyPathField = $("#key-path-field");
const keyPath = $<HTMLInputElement>("#key-path");
const secret = $<HTMLInputElement>("#secret");
const secretLabel = $<HTMLLabelElement>("#secret-label");
const secretHint = $("#secret-hint");
const credentialResult = $<HTMLOutputElement>("#credential-result");
const credentialDelete = $<HTMLButtonElement>("#credential-delete");
const credentialSave = $<HTMLButtonElement>("#credential-save");
const snapshot = document.querySelector<HTMLElement>("#snapshot")!;
const snapshotRoot = document.querySelector<HTMLElement>("#snapshot-root")!;
const snapshotWorkspaces = document.querySelector<HTMLElement>("#snapshot-workspaces")!;
const snapshotProjects = document.querySelector<HTMLElement>("#snapshot-projects")!;
const snapshotList = document.querySelector<HTMLElement>("#snapshot-list")!;
const contextWorkspaceList = el("div", { className: "item-list context-workspace-list" });
snapshot.insertBefore(contextWorkspaceList, snapshotList);
const contextMap = document.querySelector<HTMLElement>("#context-map")!;
const parentRepository = document.querySelector<HTMLSelectElement>("#parent-repository")!;
const parentPath = document.querySelector<HTMLInputElement>("#parent-path")!;
const parentBranch = document.querySelector<HTMLInputElement>("#parent-branch")!;
const parentPlanButton = document.querySelector<HTMLButtonElement>("#parent-plan")!;
const parentApplyButton = document.querySelector<HTMLButtonElement>("#parent-apply")!;
const parentResult = document.querySelector<HTMLOutputElement>("#parent-result")!;
let parentHead: string | undefined;
type ParentRun = { path: string; branch: string; at: string };
const PARENT_RUNS_KEY = "orcan-studio:parent-runs";
const parentRuns: ParentRun[] = (() => {
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(PARENT_RUNS_KEY) ?? "[]");
    return Array.isArray(saved) ? saved.filter((item): item is ParentRun => Boolean(item) && typeof item === "object" && typeof (item as ParentRun).path === "string" && typeof (item as ParentRun).branch === "string" && typeof (item as ParentRun).at === "string") : [];
  } catch { return []; }
})();

type ParentCandidate = { path: string; name: string; role: "worktree_parent" | "configured_mount"; worktree_count: number; readOnly: boolean; eligible: boolean; repositoryId?: string; branch?: string; dirty?: boolean; upstream?: string; ahead?: number; behind?: number };

function rememberParentRun(path: string, branch: string): void {
  const existing = parentRuns.findIndex((run) => run.path === path && run.branch === branch);
  if (existing >= 0) parentRuns.splice(existing, 1);
  parentRuns.unshift({ path, branch, at: new Date().toISOString() });
  parentRuns.splice(20);
  localStorage.setItem(PARENT_RUNS_KEY, JSON.stringify(parentRuns));
}

function parentCandidates(report: ProbeReport): ParentCandidate[] {
  return report.context.update_targets.map((target) => ({
    path: target.path, name: target.name, role: target.role,
    worktree_count: target.worktree_count, readOnly: target.read_only,
    eligible: target.eligible, repositoryId: target.repository_id, branch: target.branch, dirty: target.dirty,
    upstream: target.upstream, ahead: target.ahead, behind: target.behind,
  })).sort((left, right) => {
    if (left.role !== right.role) return left.role === "worktree_parent" ? -1 : 1;
    const leftRun = parentRuns.find((run) => run.path === left.path)?.at ?? "";
    const rightRun = parentRuns.find((run) => run.path === right.path)?.at ?? "";
    return rightRun.localeCompare(leftRun) || left.name.localeCompare(right.name);
  });
}

function renderParentRepositories(report: ProbeReport): void {
  const candidates = parentCandidates(report);
  const previousPath = parentPath.value;
  parentRepository.replaceChildren(new Option("Choose a managed repository…", ""), ...candidates.map((candidate) => {
    const run = parentRuns.find((item) => item.path === candidate.path && item.branch === (candidate.branch ?? "main"));
    const role = candidate.role === "worktree_parent" ? `worktree source · ${candidate.worktree_count} worktree${candidate.worktree_count === 1 ? "" : "s"}` : "mounted checkout · read-only update";
    const status = [role, candidate.branch, candidate.upstream ? candidate.behind ? `${candidate.behind} behind` : "up to date" : "no upstream", candidate.ahead ? `${candidate.ahead} ahead` : "", candidate.dirty ? "dirty — blocked" : "", run ? `updated ${new Date(run.at).toLocaleDateString()}` : ""].filter(Boolean).join(" · ");
    return new Option(`${candidate.name} · ${status}`, candidate.path);
  }), new Option("Other path…", "__manual__"));
  const selected = candidates.find((candidate) => candidate.path === previousPath) ?? candidates[0];
  if (!selected) return;
  parentRepository.value = selected.path;
  parentPath.hidden = true;
  parentPath.value = selected.path;
  if (!parentBranch.value || previousPath !== selected.path) parentBranch.value = selected.branch ?? "main";
}
const importSource = document.querySelector<HTMLInputElement>("#import-source")!;
const importDestination = document.querySelector<HTMLInputElement>("#import-destination")!;
const importPlanButton = document.querySelector<HTMLButtonElement>("#import-plan")!;
const importApplyButton = document.querySelector<HTMLButtonElement>("#import-apply")!;
const importResult = document.querySelector<HTMLOutputElement>("#import-result")!;
let importReady = false;
const sandboxSettings = document.querySelector<HTMLElement>("#sandbox-settings")!;
const settingsResult = document.querySelector<HTMLOutputElement>("#settings-result")!;
const settingsRefresh = document.querySelector<HTMLButtonElement>("#settings-refresh")!;
const settingsSync = document.querySelector<HTMLButtonElement>("#settings-sync")!;
const settingResources = document.querySelector<HTMLElement>("#setting-resources")!;
const settingAgents = document.querySelector<HTMLElement>("#setting-agents")!;
const demoBanner = document.querySelector<HTMLElement>("#demo-banner")!;
const navigationItems = Array.from(document.querySelectorAll<HTMLButtonElement>("[data-view-target]"));
const views = Array.from(document.querySelectorAll<HTMLElement>("[data-view]"));
const viewTitle = document.querySelector<HTMLElement>("#view-title")!;
const instanceState = document.querySelector<HTMLElement>("#instance-state")!;
const activeInstance = document.querySelector<HTMLButtonElement>("#active-instance")!;
const activeDot = document.querySelector<HTMLElement>("#active-dot")!;
const activeLabel = document.querySelector<HTMLElement>("#active-label")!;
const healthTitle = document.querySelector<HTMLElement>("#health-title")!;
const overviewRuntime = document.querySelector<HTMLElement>("#overview-runtime")!;
const overviewConfig = document.querySelector<HTMLElement>("#overview-config")!;
const overviewAgents = document.querySelector<HTMLElement>("#overview-agents")!;
const overviewAccess = document.querySelector<HTMLElement>("#overview-access")!;
const nextAction = document.querySelector<HTMLElement>("#next-action")!;
const setting = (id: string) => document.querySelector<HTMLElement>(`#${id}`)!;
const cleanupPath = document.querySelector<HTMLInputElement>("#cleanup-path")!;
const cleanupSuggestions = $("#cleanup-suggestions");
const cleanupConfirm = document.querySelector<HTMLInputElement>("#cleanup-confirm")!;
const cleanupRemoveBranch = document.querySelector<HTMLInputElement>("#cleanup-remove-branch")!;
const cleanupPlan = document.querySelector<HTMLButtonElement>("#cleanup-plan")!;
const cleanupApply = document.querySelector<HTMLButtonElement>("#cleanup-apply")!;
const cleanupResult = document.querySelector<HTMLOutputElement>("#cleanup-result")!;
const worktreeRepo = document.querySelector<HTMLSelectElement>("#worktree-repo")!;
const worktreeBranch = document.querySelector<HTMLInputElement>("#worktree-branch")!;
const worktreeWorkspaces = document.querySelector<HTMLSelectElement>("#worktree-workspaces")!;
const worktreePlan = document.querySelector<HTMLButtonElement>("#worktree-plan")!;
const worktreeApply = document.querySelector<HTMLButtonElement>("#worktree-apply")!;
const worktreeResult = document.querySelector<HTMLOutputElement>("#worktree-result")!;
const worktreeExisting = document.querySelector<HTMLElement>("#worktree-existing")!;
const jobsList = document.querySelector<HTMLElement>("#jobs-list")!;
type Job = { name: string; state: "running" | "succeeded" | "failed"; detail: string; at: string };
const jobs: Job[] = JSON.parse(localStorage.getItem("orcan-studio:jobs") ?? "[]");
function saveJobs(): void { localStorage.setItem("orcan-studio:jobs", JSON.stringify(jobs.slice(0, 50))); }
function addJob(name: string, detail: string): Job { const job = { name, detail, state: "running" as const, at: new Date().toISOString() }; jobs.unshift(job); saveJobs(); renderJobs(); return job; }
function finishJob(job: Job, state: "succeeded" | "failed", detail: string): void { job.state = state; job.detail = detail; saveJobs(); renderJobs(); }
function renderJobs(): void { jobsList.replaceChildren(...(jobs.length ? jobs.map((job) => { const row = document.createElement("div"); row.className = `job ${job.state}`; row.textContent = `${new Date(job.at).toLocaleString()} · ${job.name} · ${job.state} · ${job.detail}`; return row; }) : [Object.assign(document.createElement("p"), { className: "snapshot-shared", textContent: "No jobs yet." })])); }
let worktreeReady = false;
let cleanupReady = false;
let profiles: ConnectionProfile[] = [];
let savedCredentials: Credential[] = [];
let current: Connection | undefined;
let latestProbe = 0;
let connected = false;
// Outside the Tauri window there is no backend to invoke, so a plain browser always gets the UX preview.
const demoMode = new URLSearchParams(window.location.search).has("demo") || !("__TAURI_INTERNALS__" in window);

const demoReport: ProbeReport = {
  sandbox: { version: "0.1.0-dev" },
  host: { os: "Linux", architecture: "x86_64" },
  capabilities: { docker: true, managed_projects: true, live_reconcile: true },
  runtime: {
    docker: { container: { state: "running" }, agents: { codex: true, claude: true, gemini: true, copilot: false, cursor: true } },
    resources: { cpus: 4, memory: "8g", shm_size: "1g", tmpfs_size: "1g" },
    launch: { recorded: true, docker: false, git: true, network: null, ttyd: true, ttyd_auth: false },
  },
  paths: { home: "/home/orcan/.config/orcan", data: "/home/orcan/.config/orcan", projects_root: "/home/orcan/.config/orcan/sandbox", workspace_metadata_root: "/home/orcan/.config/orcan/workspaces", managed_worktrees_root: "/home/orcan/.config/orcan/worktrees" },
  context: {
    workspaces: [
      { name: "platform", projects: [{ name: "api", path: "/home/orcan/.config/orcan/sandbox/api", kind: "git_repository", branch: "main", dirty: false, repository_id: "api" }, { name: "web", path: "/home/orcan/.config/orcan/sandbox/web", kind: "git_repository", branch: "feature/studio", dirty: true, repository_id: "web" }] },
      { name: "mobile", projects: [{ name: "app", path: "/home/orcan/.config/orcan/sandbox/app", kind: "git_repository", branch: "main", dirty: false, repository_id: "app" }, { name: "api", path: "/home/orcan/.config/orcan/sandbox/api", kind: "git_repository", branch: "main", dirty: false, repository_id: "api" }] },
    ],
    managed_projects: ["api", "web", "app", "scratch"].map((name) => ({ path: `/home/orcan/.config/orcan/sandbox/${name}`, kind: "git_repository" })),
    repositories: [{ repository_id: "api", origin_url: "git@github.com:example/api.git", bindings: [{ workspace: "platform" }, { workspace: "mobile" }] }, { repository_id: "web", origin_url: "git@github.com:example/web.git", bindings: [{ workspace: "platform" }] }, { repository_id: "app", origin_url: "git@github.com:example/app.git", bindings: [{ workspace: "mobile" }] }],
    update_targets: [
      { name: "api", path: "/home/orcan/.config/orcan/sandbox/api", kind: "git_repository", role: "worktree_parent", worktree_count: 3, read_only: false, eligible: true, branch: "main", dirty: false, upstream: "origin/main", ahead: 0, behind: 2 },
      { name: "web", path: "/home/orcan/.config/orcan/sandbox/web", kind: "git_repository", role: "configured_mount", worktree_count: 0, read_only: true, eligible: false, branch: "feature/studio", dirty: true, upstream: "origin/feature/studio", ahead: 1, behind: 0 },
    ],
    configuration: { state: "synchronized", revision: "demo" },
  },
};

const demoStore: { profiles: ConnectionProfile[]; credentials: Credential[] } = {
  profiles: [
    { id: "demo", name: "Demo workstation", target: { kind: "local" } },
    { id: "gpu", name: "GPU box", target: { kind: "ssh", destination: "gpu.example" } },
    { id: "staging", name: "Staging VM", target: { kind: "ssh", destination: "staging.example" } },
  ],
  credentials: [],
};

function demoStoreCommand(command: string, args: Record<string, unknown>): unknown {
  const upsert = <T extends { id: string }>(items: T[], item: T) => [...items.filter((existing) => existing.id !== item.id), item];
  if (command === "list_profiles") return demoStore.profiles;
  if (command === "list_credentials") return demoStore.credentials;
  if (command === "save_profile") demoStore.profiles = upsert(demoStore.profiles, args.profile as ConnectionProfile);
  if (command === "save_credential") demoStore.credentials = upsert(demoStore.credentials, args.credential as Credential);
  if (command === "delete_profile") demoStore.profiles = demoStore.profiles.filter((item) => item.id !== args.id);
  if (command === "delete_credential") {
    const users = demoStore.profiles.filter((item) => item.credential_id === args.id).map((item) => item.name);
    if (users.length) throw new Error(`credential is used by: ${users.join(", ")}`);
    demoStore.credentials = demoStore.credentials.filter((item) => item.id !== args.id);
  }
  return null;
}

/** Read-only host report from `orcan-studio-preview snapshot`, served only by the dev server. */
const previewSnapshot: Promise<ProbeReport | undefined> = demoMode
  ? fetch("/preview-probe.json", { cache: "no-store" }).then((response) => (response.ok ? response.json() : undefined)).catch(() => undefined)
  : Promise.resolve(undefined);

/**
 * Preview snapshots can outlive the Studio that reads them.  Keep an older
 * Orcan report useful when a newly-added collection was emitted as null.
 */
function normalizeProbeReport(report: ProbeReport): ProbeReport {
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

type MembershipArgs = { action: "attach" | "detach"; workspace: string; project: string; apply: boolean };
const demoReports = new Map<string, ProbeReport>();

/** Each demo Enclave keeps its own report so membership changes stick until reload. */
async function demoReportFor(target: Target): Promise<ProbeReport> {
  const key = JSON.stringify(target);
  if (!demoReports.has(key)) {
    const snapshot = target.kind === "local" ? await previewSnapshot : undefined;
    const base = normalizeProbeReport(snapshot ?? (key.includes("gpu") ? { ...demoReport, runtime: { ...demoReport.runtime, docker: { ...demoReport.runtime.docker, container: { state: "exited" } } } } : demoReport));
    demoReports.set(key, structuredClone(base));
  }
  return demoReports.get(key)!;
}

/** Mirrors studio-settings.py: plan with blockers, then apply to the demo report. */
function demoMembership(report: ProbeReport, args: MembershipArgs): unknown {
  const workspace = report.context.workspaces.find((item) => item.name === args.workspace);
  const attached = workspace?.projects.some((project) => project.path === args.project) ?? false;
  const detach = args.action === "detach";
  const blockers = [detach && !workspace && "workspace does not exist", !detach && attached && "project is already attached", detach && workspace && !attached && "project is not attached to this workspace"].filter(Boolean);
  const plan = { creates_workspace: !workspace && !detach, changes: [...(!workspace && !detach ? [`create workspace ${args.workspace}`] : []), `${detach ? "detach" : "attach"} ${args.project} ${detach ? "from" : "to"} ${args.workspace}`, "run orcan sync"], blockers, ready: blockers.length === 0 };
  if (!args.apply) return { ok: true, plan };
  if (!plan.ready) throw new Error("apply requires a ready plan");
  if (detach) workspace!.projects = workspace!.projects.filter((project) => project.path !== args.project);
  else {
    const target = workspace ?? { name: args.workspace, projects: [] };
    if (!workspace) report.context.workspaces.push(target);
    target.projects.push({ name: args.project.split("/").pop(), path: args.project, kind: "git_repository", branch: "main", dirty: false });
  }
  return { ok: true, result: plan };
}

async function invoke<T>(command: string, _args?: unknown): Promise<T> {
  if (!demoMode) return tauriInvoke<T>(command, _args as never);
  await new Promise((resolve) => window.setTimeout(resolve, 180));
  if (/profile|credential/.test(command)) return demoStoreCommand(command, (_args ?? {}) as Record<string, unknown>) as T;
  const enclave = (_args as { enclave?: { target: Target } } | undefined)?.enclave;
  if (command === "probe" && JSON.stringify(enclave?.target).includes("staging")) throw new Error("SSH connection failed: Connection timed out");
  if (command === "probe") return structuredClone(await demoReportFor(enclave!.target)) as T;
  if (command === "membership_action") return demoMembership(await demoReportFor(enclave!.target), _args as MembershipArgs) as T;
  const root = demoReport.paths.projects_root;
  const worktrees = demoReport.paths.managed_worktrees_root;
  const responses: Record<string, unknown> = {
    parent_plan: { plan: { head: "abc1234", ready: true, blockers: [] } },
    import_plan: { plan: { destination: `${root}/new-repository`, destination_state: "absent", ready: true, blockers: [] } },
    import_apply: { result: { destination: `${root}/new-repository` } },
    worktree_plan: { plan: { destination: `${worktrees}/api/feature-context`, ready: true, blockers: [] } },
    worktree_apply: { result: { path: `${worktrees}/api/feature-context` } },
    worktree_cleanup: { plan: { ready: true, blockers: [] } },
    runtime_action: null,
  };
  return (responses[command] ?? {}) as T;
}

/** What the backend needs to run a command on an Enclave. */
function enclaveInput(connection: Connection): { target: Target; profileId?: string; credentialId?: string; username?: string } {
  return { target: connection.target, profileId: connection.profileId, credentialId: connection.credentialId, username: connection.username };
}

function describeTarget(value: Target): string {
  if (value.kind === "local") return "This computer";
  if (value.kind === "wsl2") return `WSL2 · ${value.distribution}`;
  return `SSH · ${value.destination}`;
}

function cacheKey(targetValue: Target): string {
  return `orcan-studio:snapshot:${JSON.stringify(targetValue)}`;
}

const viewTitles: Record<string, string> = { credentials: "Credentials & keys" };
const gatedViews = new Set(navigationItems.filter((item) => item.classList.contains("gated")).map((item) => item.dataset.viewTarget));
gatedViews.add("settings");
let currentView = "overview";

function canViewContexts(): boolean {
  return connected || Boolean(currentReport);
}

function showView(name: string): void {
  const target = views.find((view) => view.dataset.view === name);
  if (!target || (gatedViews.has(name) && !connected && !(name === "contexts" && canViewContexts()))) return;
  currentView = name;
  if (name === "enclaves") checkAll();
  for (const view of views) view.hidden = view !== target;
  for (const item of navigationItems) {
    const active = item.dataset.viewTarget === name;
    item.classList.toggle("active", active);
    item.toggleAttribute("aria-current", active);
  }
  viewTitle.textContent = viewTitles[name] ?? name[0].toUpperCase() + name.slice(1);
}

const healthPanel = document.querySelector<HTMLElement>(".health-panel")!;
const focusTitle = document.querySelector<HTMLElement>("#focus-title")!;
const initialFocus = { title: focusTitle.textContent, action: nextAction.textContent };
const needsManagedProjects = new Set(["repositories", "worktrees"]);

function lockStudio(): void {
  if (!connected) return;
  connected = false;
  if (gatedViews.has(currentView)) showView("overview");
  activeGroup.hidden = true;
  for (const item of navigationItems.filter((item) => item.classList.contains("gated"))) {
    item.hidden = item.dataset.viewTarget !== "contexts" || !canViewContexts();
  }
  healthPanel.hidden = true;
  enclaveMap.hidden = true;
  snapshot.hidden = true;
  sandboxSettings.hidden = true;
  focusTitle.textContent = initialFocus.title;
  nextAction.textContent = initialFocus.action;
  renderEnclaveStatus();
}

function unlockStudio(report: ProbeReport): void {
  connected = true;
  activeGroup.hidden = false;
  for (const item of navigationItems.filter((item) => item.classList.contains("gated"))) {
    item.hidden = needsManagedProjects.has(item.dataset.viewTarget ?? "") && !report.capabilities.managed_projects;
  }
  healthPanel.hidden = false;
  const step = nextStep(report);
  focusTitle.textContent = step.title;
  const agents = Object.entries(report.runtime.docker.agents ?? {}).filter(([, available]) => available).map(([name]) => name);
  healthTitle.textContent = report.runtime.docker.container.state === "running" ? "Ready" : "Attention needed";
  overviewRuntime.textContent = report.runtime.docker.container.state;
  overviewConfig.textContent = contextSourceLabel(report);
  overviewAgents.textContent = agents.length ? agents.join(", ") : "Not reported";
  overviewAccess.textContent = accessExposure(report.runtime.launch);
  nextAction.textContent = step.action;
}

const launchSummary = document.querySelector<HTMLElement>("#launch-summary")!;
const launchWarning = document.querySelector<HTMLElement>("#launch-warning")!;
const runtimeResult = document.querySelector<HTMLOutputElement>("#runtime-result")!;
const runtimeButtons = { start: "#runtime-start", restart: "#runtime-restart", stop: "#runtime-stop" } as const;
type RuntimeAction = keyof typeof runtimeButtons;
let launch: NonNullable<ProbeReport["runtime"]["launch"]> = { recorded: false };

function accessExposure(value: ProbeReport["runtime"]["launch"]): string {
  if (!value?.recorded) return "Not recorded";
  const terminal = value.ttyd ? (value.ttyd_auth ? "ttyd protected" : "ttyd public") : "no browser terminal";
  const docker = value.docker ? "Docker socket" : "no Docker socket";
  const ssh = value.git ? "Git/SSH access" : "no Git/SSH access";
  return `${terminal} · ${docker} · ${ssh}`;
}

function renderRuntime(report: ProbeReport): void {
  launch = report.runtime.launch ?? { recorded: false };
  const running = report.runtime.docker.container.state === "running";
  const flags = [launch.ttyd ? (launch.ttyd_auth ? "browser terminal (password)" : "browser terminal") : "local only", launch.docker && "Docker socket", launch.git && "git/SSH keys", launch.network && `network ${launch.network}`].filter(Boolean);
  launchSummary.textContent = launch.recorded ? `Start/Restart reuse: ${flags.join(" · ")}` : "No recorded start flags — start this Enclave once with orcan up on the instance.";
  launchWarning.hidden = !launch.ttyd;
  launchWarning.innerHTML = launch.ttyd_auth
    ? "Password-protected terminal: Studio does not store that password, so restart on the instance with <code>orcan up --resume --with-ttyd-auth USER:PASS</code>."
    : "The browser terminal is published without a password. Recommended: <code>orcan up --resume --with-ttyd-auth USER:PASS</code>.";
  document.querySelector<HTMLButtonElement>(runtimeButtons.start)!.disabled = running || !launch.recorded || !!launch.ttyd_auth;
  document.querySelector<HTMLButtonElement>(runtimeButtons.restart)!.disabled = !running || !launch.recorded || !!launch.ttyd_auth;
  document.querySelector<HTMLButtonElement>(runtimeButtons.stop)!.disabled = !running;
}

async function runRuntimeAction(action: RuntimeAction): Promise<void> {
  const privileged = [launch.docker && "the host Docker socket", launch.git && "your SSH keys"].filter(Boolean);
  if (action !== "stop" && privileged.length && !window.confirm(`This start gives agents access to ${privileged.join(" and ")}. Continue?`)) return;
  if (action === "stop" && !window.confirm("Stop the Enclave container? Running agent sessions will end.")) return;
  const label = action[0].toUpperCase() + action.slice(1);
  if (!current) return;
  const job = addJob(`Enclave ${action}`, current.label);
  for (const selector of Object.values(runtimeButtons)) document.querySelector<HTMLButtonElement>(selector)!.disabled = true;
  runtimeResult.textContent = `${label} in progress…`;
  try {
    await invoke("runtime_action", { enclave: enclaveInput(current), action });
    runtimeResult.textContent = `${label} finished. Refreshing instance…`;
    finishJob(job, "succeeded", label);
  } catch (error) {
    runtimeResult.textContent = `${label} failed: ${String(error)}`;
    finishJob(job, "failed", String(error));
  }
  void connect(current);
}

const enclaveMap = $("#enclave-map");
const contextCanvas = $("#context-canvas");
const connectionLines = document.querySelector<SVGSVGElement>("#connection-lines")!;
const traceLines = document.querySelector<SVGSVGElement>("#trace-lines")!;
const workspaceCards = $("#workspace-cards");
const sandboxTray = $("#sandbox-tray");
const mapFilterChips = $("#map-filter-chips");
const mapFocusClear = $<HTMLButtonElement>("#map-focus-clear");
const contextHealth = $("#context-health");
const workspaceInspector = $("#workspace-inspector");
const workspaceInspectorTitle = $("#workspace-inspector-title");
const workspaceInspectorState = $("#workspace-inspector-state");
const workspaceInspectorMetrics = $("#workspace-inspector-metrics");
const workspaceInspectorAgent = $("#workspace-inspector-agent");
const workspaceInspectorAdd = $<HTMLButtonElement>("#workspace-inspector-add");
const workspaceInspectorWorktree = $<HTMLButtonElement>("#workspace-inspector-worktree");
const workspaceInspectorDiscard = $<HTMLButtonElement>("#workspace-inspector-discard");
const projectInspector = $("#project-inspector");
const projectInspectorTitle = $("#project-inspector-title");
const projectInspectorState = $("#project-inspector-state");
const projectInspectorMetrics = $("#project-inspector-metrics");
const projectInspectorPath = $("#project-inspector-path");
const projectInspectorActions = $("#project-inspector-actions");
let focusedWorkspace: string | undefined;
let tracedPath: string | undefined;
let inspectedProject: { path: string; workspace?: string } | undefined;
const syncBanner = $("#sync-banner");
const planDialog = $<HTMLDialogElement>("#plan-dialog");
const applyDialog = $<HTMLDialogElement>("#apply-dialog");
const applyStatus = $("#apply-status");
const applyChanges = $("#apply-changes");
const applyConfirm = $<HTMLButtonElement>("#apply-confirm");
const planTitle = $("#plan-title");
const planNameField = $("#plan-name-field");
const planWorkspaceName = $<HTMLInputElement>("#plan-workspace-name");
const planModeField = $("#plan-mode-field");
const relationshipModeField = $("#relationship-mode-field");
const worktreeBranchField = $("#worktree-branch-field");
const worktreeBranchName = $<HTMLInputElement>("#worktree-branch-name");
const planChanges = $("#plan-changes");
const planStatus = $("#plan-status");
const planConfirm = $<HTMLButtonElement>("#plan-confirm");
const changeSet = $("#change-set");
const changeSetCount = $("#change-set-count");
const changeSetList = $("#change-set-list");
const changeSetClear = $<HTMLButtonElement>("#change-set-clear");
const changeSetApply = $<HTMLButtonElement>("#change-set-apply");
const DRAG_TYPE = "application/x-orcan-project";

function projectName(project: { name?: string; path: string }): string {
  return project.name ?? project.path.split("/").pop() ?? project.path;
}

/** Sandbox projects that no workspace references. */
function unassignedProjects(report: ProbeReport): Array<{ path: string; kind: string }> {
  const used = new Set(report.context.workspaces.flatMap((workspace) => workspace.projects.map((project) => project.path)));
  return report.context.managed_projects.filter((project) => !used.has(project.path));
}

type ProjectRef = { name: string; path: string; kind?: string };

type HealthProject = { path: string; kind?: string; writable?: boolean; dirty?: boolean; repository_id?: string };

function projectAlerts(report: ProbeReport, project: HealthProject, orphan = false): string[] {
  const alerts: string[] = [];
  if (project.kind === "missing") alerts.push("missing");
  else if (project.writable === false) alerts.push("read-only");
  if (project.dirty) alerts.push("uncommitted");
  if (orphan) alerts.push("orphan worktree");
  const source = project.repository_id
    ? report.context.update_targets.find((target) => target.repository_id === project.repository_id)
    : undefined;
  if (source?.behind) alerts.push(`source ${source.behind} behind`);
  return alerts;
}

function selectedProjectMode(): "git" | "mount" {
  return radioValue("project-mode") === "mount" ? "mount" : "git";
}

function selectedRelationshipMode(): "share" | "worktree" {
  return radioValue("relationship-mode") === "worktree" ? "worktree" : "share";
}

function projectKindIcon(project: ProjectRef): HTMLElement {
  const mount = project.kind === "directory";
  const worktree = project.kind === "git_worktree";
  const label = mount ? "Shared directory mount" : worktree ? "Git worktree" : "Git repository";
  const icon = el("span", { className: "project-kind", textContent: mount ? "▣" : worktree ? "⑂" : "⎇", title: label, ariaLabel: label });
  icon.dataset.tooltip = label;
  return icon;
}

function parentDirectory(path: string): string {
  const separator = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  return separator > 0 ? path.slice(0, separator) : path;
}

function parentLabel(path: string): string {
  return path.slice(Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\")) + 1) || path;
}

function projectChip(project: ProjectRef, extra: HTMLElement[] = [], from?: string, state: "current" | "planned" | "removing" = "current"): HTMLElement {
  const chip = el("span", { className: `project-chip ${state}`, draggable: true, title: `${project.path}\nDrag onto a workspace to add it` }, el("span", { className: "connection-anchor", ariaHidden: "true" }), el("span", { className: "grip", textContent: "⠿" }), projectKindIcon(project), el("span", { className: "project-name", textContent: project.name }), ...extra);
  chip.dataset.projectPath = project.path;
  chip.dataset.workspace = from ?? "sandbox";
  chip.dataset.connectionState = state;
  chip.classList.toggle("traced", tracedPath === project.path);
  chip.classList.toggle("dimmed", Boolean(tracedPath) && tracedPath !== project.path);
  chip.addEventListener("dragstart", (event) => {
    event.dataTransfer!.setData(DRAG_TYPE, JSON.stringify({ ...project, from }));
    event.dataTransfer!.effectAllowed = "copy";
    document.body.classList.add("dragging-project");
  });
  chip.addEventListener("dragend", () => document.body.classList.remove("dragging-project"));
  chip.addEventListener("click", () => {
    tracedPath = tracedPath === project.path ? undefined : project.path;
    inspectedProject = { path: project.path, workspace: from };
    if (currentReport) renderEnclaveMap(currentReport);
  });
  return chip;
}

function drawConnections(): void {
  const bounds = contextCanvas.getBoundingClientRect();
  connectionLines.replaceChildren();
  traceLines.replaceChildren();
  for (const layer of [connectionLines, traceLines]) layer.setAttribute("viewBox", `0 0 ${bounds.width} ${bounds.height}`);
  for (const source of sandboxTray.querySelectorAll<HTMLElement>(".project-chip[data-project-path]")) {
    const sourceAnchor = source.querySelector<HTMLElement>(".connection-anchor");
    if (!sourceAnchor) continue;
    const sourceBox = sourceAnchor.getBoundingClientRect();
    if (!sourceBox.width || !sourceBox.height) continue;
    const path = source.dataset.projectPath;
    for (const target of workspaceCards.querySelectorAll<HTMLElement>(`.project-chip[data-project-path="${CSS.escape(path ?? "")}"]`)) {
      const targetAnchor = target.querySelector<HTMLElement>(".connection-anchor");
      if (!targetAnchor) continue;
      const targetBox = targetAnchor.getBoundingClientRect();
      const line = document.createElementNS("http://www.w3.org/2000/svg", "path");
      const startX = sourceBox.left - bounds.left + sourceBox.width / 2;
      const startY = sourceBox.top - bounds.top;
      const endX = targetBox.left - bounds.left + targetBox.width / 2;
      const endY = targetBox.bottom - bounds.top;
      const horizontal = window.matchMedia("(min-width: 761px)").matches;
      const middleX = (startX + endX) / 2;
      const middleY = (startY + endY) / 2;
      line.setAttribute("d", horizontal
        ? `M ${startX} ${startY} C ${middleX} ${startY}, ${middleX} ${endY}, ${endX} ${endY}`
        : `M ${startX} ${startY} C ${startX} ${middleY}, ${endX} ${middleY}, ${endX} ${endY}`);
      const highlighted = tracedPath === path || target.dataset.workspace === focusedWorkspace;
      line.setAttribute("class", `context-link ${target.dataset.connectionState ?? "current"} ${highlighted ? "highlight" : "muted"}`);
      (highlighted ? traceLines : connectionLines).append(line);
    }
  }
}

function dropZone(zone: HTMLElement, onDrop: (project: ProjectRef) => void): void {
  zone.addEventListener("dragover", (event) => {
    if (!event.dataTransfer?.types.includes(DRAG_TYPE)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    zone.classList.add("drop-target");
  });
  zone.addEventListener("dragleave", (event) => { if (!zone.contains(event.relatedTarget as Node)) zone.classList.remove("drop-target"); });
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("drop-target");
    const raw = event.dataTransfer?.getData(DRAG_TYPE);
    if (raw) onDrop(JSON.parse(raw) as ProjectRef);
  });
}

/** Click alternative to dragging: a menu of workspaces to add the project to. */
function addToMenu(project: ProjectRef, report: ProbeReport): HTMLElement {
  const select = el("select", { className: "add-to", title: "Add to a workspace" });
  select.append(new Option("⋯", ""), ...report.context.workspaces.filter((workspace) => !workspace.projects.some((item) => item.path === project.path)).map((workspace) => new Option(`Add to ${workspace.name}`, workspace.name)), new Option("Add to a new workspace…", "__new__"));
  select.addEventListener("change", () => {
    const choice = select.value;
    select.value = "";
    if (choice) void reviewChange("attach", choice === "__new__" ? undefined : choice, project);
  });
  return select;
}

function renderEnclaveMap(report: ProbeReport): void {
  enclaveMap.hidden = false;
  mapFocusClear.hidden = !focusedWorkspace;
  renderWorkspaceInspector(report);
  renderProjectInspector(report);
  const query = "";
  const matches = (..._values: Array<string | undefined>) => true;
  const used = new Set(report.context.workspaces.flatMap((workspace) => workspace.projects.map((project) => project.path)));
  const plannedPaths = new Set(queuedForCurrent().filter((change) => change.action === "attach").map((change) => change.project.path));
  const sourceMatchesFilters = (project: HealthProject) => [...activeMapFilters].every((filter) => {
    if (filter === "git") return project.kind === "git_repository" || project.kind === "git_worktree";
    if (filter === "worktree") return project.kind === "git_worktree" || project.path.startsWith(report.paths.managed_worktrees_root);
    if (filter === "mount") return project.kind === "directory";
    if (filter === "unassigned") return !used.has(project.path);
    if (filter === "dirty") return Boolean(project.dirty);
    if (filter === "planned") return plannedPaths.has(project.path);
    const orphan = project.path.startsWith(report.paths.managed_worktrees_root) && !used.has(project.path);
    if (filter === "orphan") return orphan;
    return projectAlerts(report, project, orphan).length > 0;
  });
  const healthProjects = new Map<string, HealthProject>();
  for (const project of report.context.managed_projects) healthProjects.set(project.path, project);
  for (const workspace of report.context.workspaces) {
    for (const project of workspace.projects) healthProjects.set(project.path, project);
  }
  const healthIssues = [...healthProjects.values()].flatMap((project) => projectAlerts(report, project, project.path.startsWith(report.paths.managed_worktrees_root) && !used.has(project.path)));
  contextHealth.textContent = healthIssues.length
    ? `Context health: ${healthIssues.length} attention item${healthIssues.length === 1 ? "" : "s"} · ${[...new Set(healthIssues)].join(" · ")}.`
    : "Context health: no missing paths, local changes, read-only mounts, orphan worktrees, or stale branch sources.";
  const sharedIn = new Map(report.context.repositories.map((repository) => [repository.repository_id, repository.bindings.map((binding) => binding.workspace)]));
  const cards = report.context.workspaces.flatMap((workspace) => {
    if (focusedWorkspace && workspace.name !== focusedWorkspace) return [];
    const drafts = workspaceDrafts(workspace.name);
    const workspaceMatches = matches(workspace.name);
    const projects = workspace.projects
      .filter((project) => sourceMatchesFilters(project) && (workspaceMatches || matches(project.name, project.path, project.branch)))
      .sort((left, right) => parentDirectory(left.path).localeCompare(parentDirectory(right.path)) || projectName(left).localeCompare(projectName(right)));
    const visibleDrafts = drafts.filter((draft) => sourceMatchesFilters({ ...draft.project, dirty: false }) && (workspaceMatches || matches(draft.project.name, draft.project.path, draft.branch)));
    if ((query || activeMapFilters.size) && !projects.length && !visibleDrafts.length) return [];
    const meta = el("div", { className: "workspace-meta" }, el("span", { textContent: `${workspace.projects.length} project${workspace.projects.length === 1 ? "" : "s"}` }));
    if (drafts.length) meta.append(el("span", { className: "tag draft", textContent: `${drafts.length} draft${drafts.length === 1 ? "" : "s"}` }), actionButton("Discard", () => discardWorkspaceDraft(workspace.name), "workspace-draft-discard"));
    const card = el("article", { className: "workspace-card" }, el("header", {}, el("strong", { textContent: workspace.name }), meta));
    card.classList.toggle("focused", focusedWorkspace === workspace.name);
    card.title = "Click empty space to focus this workspace";
    card.addEventListener("click", (event) => {
      if ((event.target as HTMLElement).closest("button, select, input, .project-chip")) return;
      focusedWorkspace = focusedWorkspace === workspace.name ? undefined : workspace.name;
      renderEnclaveMap(report);
    });
    const list = el("div", { className: "workspace-parent-groups" });
    const projectGroups = new Map<string, HTMLUListElement>();
    for (const project of projects) {
      const ref = { name: projectName(project), path: project.path, kind: project.kind };
      const others = (project.repository_id ? sharedIn.get(project.repository_id) ?? [] : []).filter((name) => name !== workspace.name);
      const removing = drafts.some((draft) => draft.action === "detach" && draft.project.path === project.path);
      const alertTags = projectAlerts(report, project).filter((alert) => alert !== "uncommitted" && alert !== "missing");
      const tags = [project.branch && el("span", { className: "tag", textContent: project.branch }), project.dirty && el("span", { className: "tag warn", textContent: "uncommitted" }), project.kind === "missing" && el("span", { className: "tag danger", textContent: "missing" }), ...alertTags.map((alert) => el("span", { className: "tag warn", textContent: alert })), others.length > 0 && el("span", { className: "tag", textContent: `also in ${others.join(", ")}` }), removing && el("span", { className: "tag removing", textContent: "detach planned" })].filter((tag): tag is HTMLSpanElement => Boolean(tag));
      const remove = actionButton("✕", () => void reviewChange("detach", workspace.name, ref), "chip-remove");
      remove.title = `Remove ${ref.name} from ${workspace.name} (files stay)`;
      const parent = parentDirectory(project.path);
      const projectList = projectGroups.get(parent) ?? projectGroups.set(parent, el("ul")).get(parent)!;
      projectList.append(el("li", {}, projectChip(ref, tags, workspace.name, removing ? "removing" : "current"), remove, el("small", { textContent: project.path })));
    }
    for (const [parent, projectList] of [...projectGroups.entries()].sort(([left], [right]) => left.localeCompare(right))) {
      list.append(el("details", { className: "workspace-parent", open: true }, el("summary", { title: parent }, el("span", { textContent: parentLabel(parent) }), el("small", { textContent: `${projectList.children.length} project${projectList.children.length === 1 ? "" : "s"}` })), projectList));
    }
    for (const draft of visibleDrafts.filter((draft) => draft.action === "attach")) {
      const tag = el("span", { className: "tag draft", textContent: draft.relationship === "worktree" ? `new ${draft.branch}` : "planned" });
      list.append(el("li", { className: "planned-project" }, projectChip(draft.project, [tag], workspace.name, "planned"), el("small", { textContent: "Not applied yet" })));
    }
    card.append(projects.length || visibleDrafts.length ? list : el("p", { className: "hint", textContent: "Empty — drop a project here." }));
    dropZone(card, (project) => void reviewChange("attach", workspace.name, project));
    return [card];
  });
  const existingWorkspaces = new Set(report.context.workspaces.map((workspace) => workspace.name));
  const plannedWorkspaceGroups = Object.entries(groupWorkspaceDrafts()) as Array<[string, QueuedChange[]]>;
  for (const [workspace, drafts] of plannedWorkspaceGroups.filter(([name, entries]) => !existingWorkspaces.has(name) && (!focusedWorkspace || focusedWorkspace === name) && (matches(name) || entries.some((draft) => sourceMatchesFilters({ ...draft.project, dirty: false }) && matches(draft.project.name, draft.project.path, draft.branch))))) {
    const meta = el("div", { className: "workspace-meta" }, el("span", { className: "tag draft", textContent: "draft workspace" }), actionButton("Discard", () => discardWorkspaceDraft(workspace), "workspace-draft-discard"));
    const card = el("article", { className: "workspace-card planned-workspace" }, el("header", {}, el("strong", { textContent: workspace }), meta));
    const additions = drafts.filter((draft) => draft.action === "attach");
    card.append(additions.length
      ? el("ul", {}, ...additions.map((draft) => el("li", {}, projectChip(
        draft.project,
        [el("span", { className: "tag draft", textContent: draft.relationship === "worktree" ? `new ${draft.branch}` : "planned" })],
        workspace,
        "planned",
      ))))
      : el("p", { className: "hint", textContent: "No projects are planned for this workspace." }));
    cards.push(card);
  }
  const create = el("article", { className: "workspace-card new-workspace" }, el("strong", { textContent: "＋ New workspace" }), el("span", { className: "hint", textContent: "Drop a project here to start a workspace around it." }));
  dropZone(create, (project) => void reviewChange("attach", undefined, project));
  const visibleProjectPaths = new Set(cards.flatMap((card) => Array.from(card.querySelectorAll<HTMLElement>(".project-chip[data-project-path]")).map((chip) => chip.dataset.projectPath ?? "")));
  const dirtyPaths = new Set(report.context.workspaces.flatMap((workspace) => workspace.projects.filter((project) => project.dirty).map((project) => project.path)));
  const chips = report.context.managed_projects
    .filter((project) => sourceMatchesFilters({ ...project, dirty: dirtyPaths.has(project.path) }) && (!query || matches(project.path) || visibleProjectPaths.has(project.path)))
    .sort((left, right) => parentDirectory(left.path).localeCompare(parentDirectory(right.path)) || projectName(left).localeCompare(projectName(right)))
    .map((project) => {
    const ref = { name: projectName(project), path: project.path, kind: project.kind };
    const connectedToFocus = focusedWorkspace && report.context.workspaces.find((workspace) => workspace.name === focusedWorkspace)?.projects.some((item) => item.path === project.path);
    const alerts = projectAlerts(report, { ...project, dirty: dirtyPaths.has(project.path) }, project.path.startsWith(report.paths.managed_worktrees_root) && !used.has(project.path));
    const tags = [!used.has(project.path) && el("span", { className: "tag warn", textContent: "no workspace" }), ...alerts.map((alert) => el("span", { className: "tag warn", textContent: alert })), connectedToFocus && el("span", { className: "tag connected", textContent: "connected" })].filter((tag): tag is HTMLElement => Boolean(tag));
    const chip = projectChip(ref, tags);
    const action = focusedWorkspace
      ? connectedToFocus
        ? el("span", { className: "focus-attached", textContent: "✓", title: `Already connected to ${focusedWorkspace}` })
        : actionButton("+", () => void reviewChange("attach", focusedWorkspace, ref), "attach-to-focus")
      : addToMenu(ref, report);
    if (action instanceof HTMLButtonElement) action.title = `Add ${ref.name} to ${focusedWorkspace}`;
    return { parent: parentDirectory(project.path), item: el("span", { className: "tray-item" }, chip, action) };
    });
  const showCreate = !focusedWorkspace && activeMapFilters.size === 0;
  workspaceCards.replaceChildren(...(cards.length ? cards : [el("p", { className: "hint map-empty", textContent: "No workspace or planned relation matches this filter." })]), ...(showCreate ? [create] : []));
  const groups = chips.reduce<Map<string, HTMLElement[]>>((all, chip) => {
    (all.get(chip.parent) ?? all.set(chip.parent, []).get(chip.parent)!).push(chip.item);
    return all;
  }, new Map());
  const groupNodes = [...groups.entries()].map(([parent, items]) => el("details", { className: "project-parent", open: true }, el("summary", { title: parent }, el("span", { textContent: parentLabel(parent) }), el("small", { textContent: `${items.length} project${items.length === 1 ? "" : "s"}` })), el("div", { className: "tray-chips" }, ...items)));
  sandboxTray.replaceChildren(el("div", { className: "tray-header" }, el("strong", { textContent: `Available elements (${chips.length})` }), el("span", { className: "hint", textContent: `${report.paths.projects_root}` })), groupNodes.length ? el("div", { className: "project-parent-groups" }, ...groupNodes) : el("p", { className: "hint", textContent: query ? "No available element matches this filter." : "No projects in the sandbox yet. Import one in Repositories." }));
  requestAnimationFrame(drawConnections);
}

function renderWorkspaceInspector(report: ProbeReport): void {
  const workspace = report.context.workspaces.find((item) => item.name === focusedWorkspace);
  workspaceInspector.hidden = !workspace;
  if (!workspace) return;
  const drafts = workspaceDrafts(workspace.name);
  const worktrees = workspace.projects.filter((project) => project.kind === "git_worktree" || project.path.startsWith(report.paths.managed_worktrees_root)).length;
  const mounts = workspace.projects.filter((project) => project.kind === "directory").length;
  const dirty = workspace.projects.filter((project) => project.dirty).length;
  const missing = workspace.projects.filter((project) => project.kind === "missing").length;
  const names = [...workspace.projects.map(projectName), ...drafts.filter((draft) => draft.action === "attach").map((draft) => draft.project.name)];
  workspaceInspectorTitle.textContent = workspace.name;
  workspaceInspectorState.textContent = drafts.length ? `${drafts.length} planned change${drafts.length === 1 ? "" : "s"}` : "No pending changes";
  workspaceInspectorMetrics.replaceChildren(
    el("span", { textContent: `${workspace.projects.length} elements` }),
    el("span", { textContent: `${worktrees} worktrees` }),
    el("span", { textContent: `${mounts} mounts` }),
    el("span", { className: dirty || missing ? "warn" : "", textContent: dirty ? `${dirty} dirty` : missing ? `${missing} missing` : "ready" }),
  );
  workspaceInspectorAgent.textContent = `After applying the plan and running sync, the agent sees: ${names.length ? names.slice(0, 6).join(" · ") + (names.length > 6 ? ` · +${names.length - 6} more` : "") : "no elements yet"}.`;
  workspaceInspectorDiscard.hidden = drafts.length === 0;
  workspaceInspectorWorktree.disabled = !canEditContext(report);
}

function renderProjectInspector(report: ProbeReport): void {
  const reference = inspectedProject;
  if (!reference) {
    projectInspector.hidden = true;
    return;
  }
  const workspace = reference.workspace
    ? report.context.workspaces.find((item) => item.name === reference.workspace)
    : undefined;
  const project = workspace?.projects.find((item) => item.path === reference.path)
    ?? report.context.managed_projects.find((item) => item.path === reference.path)
    ?? report.context.workspaces.flatMap((item) => item.projects).find((item) => item.path === reference.path);
  if (!project) {
    inspectedProject = undefined;
    projectInspector.hidden = true;
    return;
  }
  const bindings = report.context.workspaces
    .filter((item) => item.projects.some((candidate) => candidate.path === project.path))
    .map((item) => item.name);
  const alerts = projectAlerts(report, project, project.path.startsWith(report.paths.managed_worktrees_root) && bindings.length === 0);
  projectInspector.hidden = false;
  projectInspectorTitle.textContent = projectName(project);
  projectInspectorState.textContent = [project.kind, project.branch, ...alerts].filter(Boolean).join(" · ") || "No Git details reported";
  projectInspectorMetrics.replaceChildren(
    el("span", { textContent: `${bindings.length} workspace${bindings.length === 1 ? "" : "s"}` }),
    el("span", { textContent: project.writable === false ? "read-only" : "writable" }),
    el("span", { className: project.dirty ? "warn" : "", textContent: project.dirty ? "uncommitted" : "clean" }),
  );
  projectInspectorPath.textContent = project.path;
  const actions: HTMLElement[] = [];
  if (reference.workspace && bindings.includes(reference.workspace)) {
    actions.push(actionButton(`Detach from ${reference.workspace}`, () => void reviewChange("detach", reference.workspace, { name: projectName(project), path: project.path, kind: project.kind })));
  }
  if (focusedWorkspace && !bindings.includes(focusedWorkspace)) {
    actions.push(actionButton(`Add to ${focusedWorkspace}`, () => void reviewChange("attach", focusedWorkspace, { name: projectName(project), path: project.path, kind: project.kind }), "secondary"));
  }
  if ((project.kind === "git_repository" || project.kind === "git_worktree") && canEditContext(report)) {
    actions.push(actionButton("New worktree", () => {
      showView("worktrees");
      const source = parentCandidates(report).find((candidate) => candidate.repositoryId === project.repository_id && candidate.eligible);
      if (source) worktreeRepo.value = source.path;
      for (const option of worktreeWorkspaces.options) option.selected = option.value === (reference.workspace ?? focusedWorkspace);
      renderWorktreeExisting();
      worktreeBranch.focus();
    }, "secondary"));
  }
  actions.push(actionButton("Clear", () => { inspectedProject = undefined; tracedPath = undefined; renderEnclaveMap(report); }, "secondary"));
  for (const action of actions) {
    if (!canEditContext(report) && action.textContent !== "Clear" && action instanceof HTMLButtonElement) action.disabled = true;
  }
  projectInspectorActions.replaceChildren(...actions);
}

window.addEventListener("resize", () => { if (currentReport) requestAnimationFrame(drawConnections); });
type MapFilter = "attention" | "git" | "worktree" | "mount" | "unassigned" | "dirty" | "planned" | "orphan";
const activeMapFilters = new Set<MapFilter>();
for (const button of mapFilterChips.querySelectorAll<HTMLButtonElement>("[data-map-filter]")) {
  button.addEventListener("click", () => {
    const filter = button.dataset.mapFilter as MapFilter;
    activeMapFilters.has(filter) ? activeMapFilters.delete(filter) : activeMapFilters.add(filter);
    button.classList.toggle("active", activeMapFilters.has(filter));
    if (currentReport) renderEnclaveMap(currentReport);
  });
}
mapFocusClear.addEventListener("click", () => { focusedWorkspace = undefined; if (currentReport) renderEnclaveMap(currentReport); });
workspaceInspectorAdd.addEventListener("click", () => sandboxTray.scrollIntoView({ behavior: "smooth", block: "nearest" }));
workspaceInspectorWorktree.addEventListener("click", () => {
  if (!focusedWorkspace) return;
  showView("worktrees");
  for (const option of worktreeWorkspaces.options) option.selected = option.value === focusedWorkspace;
  renderWorktreeExisting();
  worktreeRepo.focus();
});
workspaceInspectorDiscard.addEventListener("click", () => { if (focusedWorkspace) discardWorkspaceDraft(focusedWorkspace); });

type PendingChange = { action: MembershipArgs["action"]; workspace?: string; project: ProjectRef };
type QueuedChange = PendingChange & {
  id: string;
  enclave: string;
  workspace: string;
  projectMode: "git" | "mount";
  relationship: "share" | "worktree";
  branch?: string;
  changes: string[];
  error?: string;
};

let pendingChange: PendingChange | undefined;
let pendingPlan: { ready: boolean; changes: string[] } | undefined;
const DRAFT_STORAGE_KEY = "orcan-studio:context-drafts";

function isQueuedChange(value: unknown): value is QueuedChange {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<QueuedChange>;
  return typeof item.id === "string" && typeof item.enclave === "string" && (item.action === "attach" || item.action === "detach") && typeof item.workspace === "string" && typeof item.project?.path === "string" && typeof item.project?.name === "string" && (item.projectMode === "git" || item.projectMode === "mount") && (item.relationship === "share" || item.relationship === "worktree") && Array.isArray(item.changes);
}

function loadQueuedChanges(): QueuedChange[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(DRAFT_STORAGE_KEY) ?? "[]");
    return Array.isArray(value) ? value.filter(isQueuedChange) : [];
  } catch { return []; }
}

function saveQueuedChanges(): void {
  localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(queuedChanges));
  renderEnclaveStatus();
}

const queuedChanges: QueuedChange[] = loadQueuedChanges();
const restoredDraftIds = new Set(queuedChanges.map((change) => change.id));

function enclaveChangeKey(connection: Connection): string {
  return JSON.stringify({ target: connection.target, username: connection.username, credentialId: connection.credentialId });
}

function queuedForCurrent(): QueuedChange[] {
  const connection = current;
  return connection ? queuedChanges.filter((change) => change.enclave === enclaveChangeKey(connection)) : [];
}

function groupWorkspaceDrafts(): Record<string, QueuedChange[]> {
  return queuedForCurrent().reduce<Record<string, QueuedChange[]>>((groups, change) => {
    (groups[change.workspace] ??= []).push(change);
    return groups;
  }, {});
}

function workspaceDrafts(workspace: string): QueuedChange[] {
  return groupWorkspaceDrafts()[workspace] ?? [];
}

function queueConflicts(changes: QueuedChange[]): Map<string, string> {
  const conflicts = new Map<string, string>();
  const relationships = new Map<string, QueuedChange[]>();
  const worktrees = new Map<string, QueuedChange[]>();
  for (const change of changes) {
    const relationship = `${change.workspace}\u0000${change.project.path}`;
    (relationships.get(relationship) ?? relationships.set(relationship, []).get(relationship)!).push(change);
    if (change.action === "attach" && change.relationship === "worktree" && change.branch) {
      const worktree = `${change.project.path}\u0000${change.branch}`;
      (worktrees.get(worktree) ?? worktrees.set(worktree, []).get(worktree)!).push(change);
    }
  }
  for (const entries of relationships.values()) {
    if (new Set(entries.map((change) => change.action)).size > 1) {
      for (const change of entries) conflicts.set(change.id, "Conflicts with an attach/detach draft for the same workspace and element.");
    }
  }
  for (const entries of worktrees.values()) {
    if (entries.length > 1) {
      for (const change of entries) conflicts.set(change.id, "Another draft creates a worktree from this repository with the same branch.");
    }
  }
  return conflicts;
}

function discardWorkspaceDraft(workspace: string): void {
  const drafts = workspaceDrafts(workspace);
  if (!drafts.length || !current) return;
  const noun = drafts.length === 1 ? "change" : "changes";
  if (!window.confirm(`Discard ${drafts.length} planned ${noun} for ${workspace}? Nothing has been applied to Orcan.`)) return;
  const key = enclaveChangeKey(current);
  for (let index = queuedChanges.length - 1; index >= 0; index -= 1) {
    if (queuedChanges[index].enclave === key && queuedChanges[index].workspace === workspace) restoredDraftIds.delete(queuedChanges.splice(index, 1)[0].id);
  }
  saveQueuedChanges();
  renderChangeSet();
  result.textContent = `Discarded planned changes for ${workspace}.`;
}

function changeTitle(change: QueuedChange): string {
  if (change.action === "detach") return `Detach ${change.project.name} from ${change.workspace}`;
  if (change.relationship === "worktree") return `Create ${change.branch} for ${change.workspace}`;
  return `Add ${change.project.name} to ${change.workspace}`;
}

function renderChangeSet(): void {
  const changes = queuedForCurrent();
  const conflicts = queueConflicts(changes);
  changeSet.hidden = changes.length === 0;
  changeSetCount.textContent = `${changes.length} change${changes.length === 1 ? "" : "s"}${conflicts.size ? ` · ${conflicts.size} conflict${conflicts.size === 1 ? "" : "s"}` : ""}`;
  changeSetApply.textContent = `Apply ${changes.length} change${changes.length === 1 ? "" : "s"}`;
  changeSetApply.disabled = changes.length === 0 || conflicts.size > 0 || !canEditContext();
  changeSetClear.disabled = changes.length === 0;
  changeSetList.replaceChildren(...changes.map((change) => {
    const conflict = conflicts.get(change.id);
    const detail = conflict ?? change.error ?? (restoredDraftIds.has(change.id) ? "Saved draft — recheck before applying" : change.changes.join(" · "));
    const remove = actionButton("Remove", () => {
      const index = queuedChanges.findIndex((item) => item.id === change.id);
      if (index >= 0) queuedChanges.splice(index, 1);
      restoredDraftIds.delete(change.id);
      saveQueuedChanges();
      renderChangeSet();
    });
    const recheck = actionButton("Recheck", () => void recheckQueuedChange(change), "secondary");
    return el("div", { className: `change-set-item${change.error || conflict ? " failed" : ""}` }, el("div", {}, el("strong", { textContent: changeTitle(change) }), el("span", { textContent: detail })), el("div", { className: "change-set-actions" }, recheck, remove));
  }));
  if (currentReport) renderEnclaveMap(currentReport);
}

async function planChange(): Promise<void> {
  if (!pendingChange || !current) return;
  const workspace = pendingChange.workspace ?? planWorkspaceName.value.trim();
  planConfirm.disabled = true;
  pendingPlan = undefined;
  planChanges.replaceChildren();
  if (!/^[A-Za-z0-9._-]{1,64}$/.test(workspace)) { planStatus.textContent = "Enter a workspace name."; return; }
  planStatus.textContent = "Asking Orcan for a plan…";
  try {
    const response = pendingChange.action === "attach" && selectedRelationshipMode() === "worktree"
      ? await invoke<{ plan: { changes: string[]; blockers: string[]; ready: boolean } }>("worktree_plan", { enclave: enclaveInput(current), repo: pendingChange.project.path, branch: worktreeBranchName.value.trim(), worktreesRoot: setting("setting-worktrees-root").textContent, workspaces: [workspace] })
      : await invoke<{ plan: { changes: string[]; blockers: string[]; ready: boolean } }>("membership_action", { enclave: enclaveInput(current), action: pendingChange.action, workspace, project: pendingChange.project.path, projectMode: selectedProjectMode(), apply: false });
    planChanges.replaceChildren(...response.plan.changes.map((change) => el("li", { textContent: change })), ...response.plan.blockers.map((blocker) => el("li", { className: "blocker", textContent: blocker })));
    planStatus.textContent = response.plan.ready ? `Applies to ${current.label}. Nothing else changes.` : "Orcan cannot apply this change.";
    pendingPlan = { ready: response.plan.ready, changes: response.plan.changes };
    planConfirm.disabled = !response.plan.ready;
  } catch (error) { planStatus.textContent = `Plan failed: ${String(error)}`; }
}

/** Opens the review dialog; nothing changes until the user confirms Orcan's plan. */
async function reviewChange(action: MembershipArgs["action"], workspace: string | undefined, project: ProjectRef): Promise<void> {
  if (!canEditContext()) {
    result.textContent = contextEditMessage();
    return;
  }
  if (action === "attach" && workspace && currentReport?.context.workspaces.find((item) => item.name === workspace)?.projects.some((item) => item.path === project.path)) {
    result.textContent = `${project.name} is already in ${workspace}.`;
    return;
  }
  pendingChange = { action, workspace, project };
  planTitle.textContent = action === "detach" ? `Remove ${project.name} from ${workspace}` : workspace ? `Add ${project.name} to ${workspace}` : `New workspace with ${project.name}`;
  planNameField.hidden = workspace !== undefined;
  const gitProject = project.kind === "git_repository" || project.kind === "git_worktree";
  relationshipModeField.hidden = action === "detach" || !gitProject;
  worktreeBranchField.hidden = action === "detach" || !gitProject || selectedRelationshipMode() !== "worktree";
  setRadio("relationship-mode", "share");
  worktreeBranchName.value = `feature/${workspace ?? project.name}`.replace(/[^A-Za-z0-9._/-]+/g, "-");
  planModeField.hidden = action === "detach";
  setRadio("project-mode", project.kind === "directory" ? "mount" : "git");
  planWorkspaceName.value = workspace ? "" : project.name.toLowerCase().replace(/[^a-z0-9._-]+/g, "-");
  planDialog.showModal();
  await planChange();
}

function queueChange(): void {
  if (!pendingChange || !pendingPlan?.ready || !current) return;
  const workspace = pendingChange.workspace ?? planWorkspaceName.value.trim();
  const { action, project } = pendingChange;
  const relationship = action === "attach" ? selectedRelationshipMode() : "share";
  const branch = relationship === "worktree" ? worktreeBranchName.value.trim() : undefined;
  const duplicate = queuedForCurrent().some((change) => change.action === action && change.workspace === workspace && change.project.path === project.path && change.relationship === relationship && change.branch === branch);
  if (duplicate) {
    planStatus.textContent = "This exact change is already in the plan.";
    return;
  }
  queuedChanges.push({ id: newId(), enclave: enclaveChangeKey(current), action, workspace, project, projectMode: selectedProjectMode(), relationship, branch, changes: pendingPlan.changes });
  saveQueuedChanges();
  planDialog.close();
  renderChangeSet();
  result.textContent = `${changeTitle(queuedChanges.at(-1)!)} is ready to apply.`;
}

async function applyQueuedChanges(selectedIds?: Set<string>): Promise<void> {
  const connection = current;
  if (!connection) return;
  if (!canEditContext()) {
    result.textContent = contextEditMessage();
    return;
  }
  const enclave = enclaveChangeKey(connection);
  const changes = queuedChanges.filter((change) => change.enclave === enclave && (!selectedIds || selectedIds.has(change.id)));
  if (!changes.length) return;
  if (queueConflicts(changes).size) {
    result.textContent = "Resolve the conflicting planned changes before applying them.";
    renderChangeSet();
    return;
  }
  const worktreesRoot = setting("setting-worktrees-root").textContent;
  changeSetApply.disabled = true;
  changeSetClear.disabled = true;
  for (const change of changes) {
    const job = addJob("Apply planned context change", changeTitle(change));
    try {
      await revalidateQueuedChange(change, connection, worktreesRoot);
      if (change.action === "attach" && change.relationship === "worktree") {
        await invoke("worktree_apply", { enclave: enclaveInput(connection), repo: change.project.path, branch: change.branch, worktreesRoot, workspaces: [change.workspace] });
      } else {
        await invoke("membership_action", { enclave: enclaveInput(connection), action: change.action, workspace: change.workspace, project: change.project.path, projectMode: change.projectMode, apply: true });
      }
      const index = queuedChanges.findIndex((item) => item.id === change.id);
      if (index >= 0) queuedChanges.splice(index, 1);
      restoredDraftIds.delete(change.id);
      saveQueuedChanges();
      finishJob(job, "succeeded", changeTitle(change));
      if (current && enclaveChangeKey(current) === enclave) syncBanner.hidden = false;
    } catch (error) {
      change.error = String(error);
      saveQueuedChanges();
      finishJob(job, "failed", change.error);
    }
    renderChangeSet();
  }
  if (current && enclaveChangeKey(current) === enclave) {
    result.textContent = queuedChanges.some((change) => change.enclave === enclave && change.error) ? "Some planned changes could not be applied; review the marked entries." : "Context changes applied. Run orcan sync to update the Enclave mounts.";
    await connect(connection).catch(() => undefined);
  }
  renderChangeSet();
}

function openApplyReview(): void {
  const changes = queuedForCurrent();
  if (!changes.length || queueConflicts(changes).size) return;
  applyChanges.replaceChildren(...changes.map((change) => {
    const checkbox = el("input", { type: "checkbox", checked: true, value: change.id });
    return el("li", { className: "apply-choice" }, el("label", {}, checkbox, el("span", { textContent: changeTitle(change) })));
  }));
  applyStatus.textContent = `${changes.length} change${changes.length === 1 ? "" : "s"} will be rechecked with Orcan immediately before execution. Nothing has changed yet.`;
  applyDialog.showModal();
}

async function revalidateQueuedChange(change: QueuedChange, connection: Connection, worktreesRoot: string): Promise<void> {
  const response = change.action === "attach" && change.relationship === "worktree"
    ? await invoke<{ plan: { changes: string[]; blockers: string[]; ready: boolean } }>("worktree_plan", { enclave: enclaveInput(connection), repo: change.project.path, branch: change.branch, worktreesRoot, workspaces: [change.workspace] })
    : await invoke<{ plan: { changes: string[]; blockers: string[]; ready: boolean } }>("membership_action", { enclave: enclaveInput(connection), action: change.action, workspace: change.workspace, project: change.project.path, projectMode: change.projectMode, apply: false });
  if (!response.plan.ready) throw new Error(response.plan.blockers.join(" · ") || "Orcan no longer accepts this planned change");
  change.changes = response.plan.changes;
  change.error = undefined;
  restoredDraftIds.delete(change.id);
  saveQueuedChanges();
}

async function recheckQueuedChange(change: QueuedChange): Promise<void> {
  const connection = current;
  if (!connection || change.enclave !== enclaveChangeKey(connection)) {
    change.error = "Open the Enclave this draft belongs to before rechecking it.";
    saveQueuedChanges();
    renderChangeSet();
    return;
  }
  try {
    await revalidateQueuedChange(change, connection, setting("setting-worktrees-root").textContent);
  } catch (error) {
    change.error = String(error);
    saveQueuedChanges();
  }
  renderChangeSet();
}

planWorkspaceName.addEventListener("input", () => void planChange());
for (const input of document.querySelectorAll<HTMLInputElement>('input[name="project-mode"]')) input.addEventListener("change", () => void planChange());
for (const input of document.querySelectorAll<HTMLInputElement>('input[name="relationship-mode"]')) input.addEventListener("change", () => { worktreeBranchField.hidden = selectedRelationshipMode() !== "worktree"; planModeField.hidden = selectedRelationshipMode() === "worktree"; void planChange(); });
worktreeBranchName.addEventListener("input", () => void planChange());
planConfirm.addEventListener("click", queueChange);
changeSetClear.addEventListener("click", () => {
  if (!current) return;
  const key = enclaveChangeKey(current);
  for (let index = queuedChanges.length - 1; index >= 0; index -= 1) if (queuedChanges[index].enclave === key) restoredDraftIds.delete(queuedChanges.splice(index, 1)[0].id);
  saveQueuedChanges();
  renderChangeSet();
});
changeSetApply.addEventListener("click", openApplyReview);
applyConfirm.addEventListener("click", () => {
  const selected = new Set(Array.from(applyChanges.querySelectorAll<HTMLInputElement>("input:checked"), (input) => input.value));
  applyDialog.close();
  void applyQueuedChanges(selected);
});
$("#sync-now").addEventListener("click", async () => {
  if (!current) return;
  const button = $<HTMLButtonElement>("#sync-now");
  button.disabled = true;
  const job = addJob("Orcan sync", current.label);
  try {
    await invoke("sync", { enclave: enclaveInput(current) });
    finishJob(job, "succeeded", "Context reconciled");
    syncBanner.hidden = true;
    result.textContent = "Sync finished; the Enclave now mounts the new workspace layout.";
    await connect(current).catch(() => undefined);
  } catch (error) { finishJob(job, "failed", String(error)); result.textContent = `Sync failed: ${String(error)}`; }
  finally { button.disabled = false; }
});

/** One sentence that says what to look at first. */
function nextStep(report: ProbeReport): { title: string; action: string } {
  const projects = report.context.workspaces.flatMap((workspace) => workspace.projects);
  const dirty = projects.filter((project) => project.dirty).length;
  const missing = projects.filter((project) => project.kind === "missing").length;
  const loose = unassignedProjects(report).length;
  const summary = `${report.context.workspaces.length} workspace${report.context.workspaces.length === 1 ? "" : "s"} · ${report.context.managed_projects.length} project${report.context.managed_projects.length === 1 ? "" : "s"} in the sandbox`;
  if (report.runtime.docker.container.state !== "running") return { title: "Container is not running", action: `${summary}. Start the Enclave to let agents work; the map below is read from its configuration.` };
  if (missing) return { title: `${missing} project path${missing === 1 ? " is" : "s are"} missing`, action: `${summary}. A workspace points at a path that does not exist on this machine; fix or detach it in Repositories.` };
  if (!report.context.workspaces.length) return { title: "No workspaces yet", action: `${summary}. Create a workspace so agents get a focused set of projects.` };
  if (loose) return { title: summary, action: `${loose} project${loose === 1 ? " is" : "s are"} in the sandbox but in no workspace. ${dirty ? `${dirty} project${dirty === 1 ? " has" : "s have"} uncommitted changes.` : "Everything else is committed."}` };
  return { title: summary, action: dirty ? `${dirty} project${dirty === 1 ? " has" : "s have"} uncommitted changes; review them before starting new work.` : "Every project is committed. Pick a workspace below or create a worktree for parallel work." };
}

let currentReport: ProbeReport | undefined;

function canEditContext(report = currentReport): boolean {
  const configuration = report?.context.configuration;
  return Boolean(configuration && (configuration.editable ?? (configuration.source === "config" || (!configuration.source && configuration.state === "present"))));
}

function contextSourceLabel(report: ProbeReport): string {
  const source = report.context.configuration.source ?? (report.context.configuration.state === "present" ? "config" : "runtime_index");
  return source === "config" ? "orcan.config.json" : source === "runtime_index" ? "synced workspace index · read-only" : "no Orcan context source";
}

function contextEditMessage(): string {
  return "This Enclave reports only its last synced workspace index. Reconnect where orcan.config.json is available before changing context.";
}

function selectedWorkspaces(): string[] {
  return Array.from(worktreeWorkspaces.selectedOptions, (option) => option.value);
}

function renderWorktreeExisting(): void {
  const report = currentReport;
  const candidate = report && parentCandidates(report).find((item) => item.path === worktreeRepo.value);
  const selected = selectedWorkspaces();
  if (!report || !candidate || !selected.length) {
    worktreeExisting.textContent = "Choose a source repository and one or more workspace families to inspect existing branches.";
    return;
  }
  const branches = selected.flatMap((workspaceName) => {
    const workspace = report.context.workspaces.find((item) => item.name === workspaceName);
    return (workspace?.projects ?? [])
      .filter((project) => project.repository_id === candidate.repositoryId && project.path.startsWith(report.paths.managed_worktrees_root))
      .map((project) => `${workspaceName} · ${project.branch ?? project.name ?? "detached"}`);
  });
  worktreeExisting.textContent = branches.length
    ? `Already connected from this source: ${branches.join(" · ")}.`
    : "No managed branches from this source are connected to the selected workspace families.";
}

function renderWorktreeChoices(report: ProbeReport): void {
  const previousRepository = worktreeRepo.value;
  const previousWorkspaces = new Set(selectedWorkspaces());
  const sources = parentCandidates(report).filter((candidate) => candidate.eligible);
  worktreeRepo.replaceChildren(
    new Option("Choose a clean Git source…", ""),
    ...sources.map((candidate) => new Option(
      `${candidate.name} · ${candidate.branch ?? "detached"}${candidate.role === "worktree_parent" ? ` · ${candidate.worktree_count} worktrees` : " · mounted source"}`,
      candidate.path,
    )),
  );
  worktreeRepo.value = sources.some((candidate) => candidate.path === previousRepository)
    ? previousRepository
    : sources[0]?.path ?? "";
  worktreeWorkspaces.replaceChildren(...report.context.workspaces.map((workspace) => new Option(`${workspace.name} · ${workspace.projects.length} projects`, workspace.name, false, previousWorkspaces.has(workspace.name) || focusedWorkspace === workspace.name)));
  renderWorktreeExisting();
}

function renderSnapshot(report: ProbeReport): void {
  report = normalizeProbeReport(report);
  currentReport = report;
  // The navigation is the essential connection result.  Map decorations and
  // inventories below are helpful, but must never keep a valid report locked.
  unlockStudio(report);
  renderEnclaveMap(report);
  snapshot.hidden = false;
  snapshotRoot.textContent = report.paths.projects_root;
  snapshotWorkspaces.textContent = String(report.context.workspaces.length);
  snapshotProjects.textContent = String(report.context.managed_projects.length);
  renderContextWorkspaceList(report);
  sandboxSettings.hidden = false;
  setting("setting-home").textContent = report.paths.home;
  setting("setting-data").textContent = report.paths.data;
  setting("setting-projects-root").textContent = report.paths.projects_root;
  setting("setting-workspaces-root").textContent = report.paths.workspace_metadata_root;
  setting("setting-worktrees-root").textContent = report.paths.managed_worktrees_root;
  setting("setting-config-state").textContent = report.context.configuration.revision ? `${contextSourceLabel(report)} · ${report.context.configuration.revision}` : contextSourceLabel(report);
  settingsSync.disabled = !canEditContext(report);
  if (!canEditContext(report)) settingsResult.textContent = contextEditMessage();
  setting("setting-access").textContent = accessExposure(report.runtime.launch);
  renderParentRepositories(report);
  renderWorktreeChoices(report);
  const resources = report.runtime.resources;
  settingResources.textContent = resources ? `CPU ${resources.cpus ?? "—"} · RAM ${resources.memory ?? "—"} · SHM ${resources.shm_size ?? "—"}` : "Not reported";
  const agents = Object.entries(report.runtime.docker.agents ?? {}).filter(([, available]) => available).map(([name]) => name);
  settingAgents.textContent = agents.length ? agents.join(" · ") : "No image manifest reported";
  const managedWorktrees = report.context.workspaces.flatMap((workspace) => workspace.projects
    .filter((project) => project.path.startsWith(report.paths.managed_worktrees_root))
    .map((project) => ({ workspace: workspace.name, project })));
  cleanupSuggestions.replaceChildren(...(managedWorktrees.length ? managedWorktrees.map(({ workspace, project }) => {
    const review = actionButton("Review", () => { cleanupPath.value = project.path; cleanupResult.textContent = `Selected ${project.name ?? project.path} from ${workspace}.`; });
    return el("div", { className: "cleanup-item" }, el("span", { textContent: `${project.name ?? project.path.split("/").pop()} · ${workspace}${project.branch ? ` · ${project.branch}` : ""}` }), review);
  }) : [el("p", { className: "hint", textContent: "No managed worktrees are currently connected to a workspace." })]));
  void refreshWorktreeInventory(report.paths.managed_worktrees_root);
  renderRuntime(report);
  const rows: HTMLElement[] = [];
  for (const workspace of report.context.workspaces) {
    const row = document.createElement("div");
    row.className = "snapshot-workspace";
    const heading = document.createElement("strong");
    heading.textContent = `${workspace.name} · ${workspace.projects.length} project${workspace.projects.length === 1 ? "" : "s"}`;
    row.append(heading);
    for (const project of workspace.projects) {
      const projectRow = document.createElement("span");
      const state = project.branch ? ` · ${project.branch}${project.dirty ? " · dirty" : ""}` : "";
      projectRow.textContent = `${project.name ?? "unnamed"} · ${project.kind}${state} · ${project.path}`;
      row.append(projectRow);
    }
    rows.push(row);
  }
  for (const repository of report.context.repositories.filter((item) => item.bindings.length > 1)) {
    const shared = document.createElement("p");
    shared.className = "snapshot-shared";
    shared.textContent = `Shared repository · ${repository.origin_url ?? repository.repository_id} · ${repository.bindings.length} context families`;
    rows.push(shared);
  }
  snapshotList.replaceChildren(...rows);
  contextMap.replaceChildren(...report.context.repositories.map((repository) => {
    const node = document.createElement("div");
    node.className = "repo-node";
    node.textContent = `${repository.origin_url ?? repository.repository_id}  →  ${repository.bindings.map((binding) => binding.workspace).join(" · ")}`;
    return node;
  }));
}

function renderContextWorkspaceList(report: ProbeReport): void {
  const editable = canEditContext(report);
  contextWorkspaceList.replaceChildren(...report.context.workspaces.map((workspace) => {
    const worktrees = workspace.projects.filter((project) => project.kind === "git_worktree" || project.path.startsWith(report.paths.managed_worktrees_root)).length;
    const dirty = workspace.projects.filter((project) => project.dirty).length;
    const state = [`${workspace.projects.length} projects`, worktrees ? `${worktrees} worktrees` : "no worktrees", dirty ? `${dirty} dirty` : "clean"].join(" · ");
    const open = actionButton("Open on map", () => {
      focusedWorkspace = workspace.name;
      showView("overview");
      renderEnclaveMap(report);
      enclaveMap.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    const add = actionButton("Add project", () => {
      focusedWorkspace = workspace.name;
      showView("overview");
      renderEnclaveMap(report);
      sandboxTray.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, "secondary");
    const worktree = actionButton("New worktree", () => {
      focusedWorkspace = workspace.name;
      showView("worktrees");
      for (const option of worktreeWorkspaces.options) option.selected = option.value === workspace.name;
      renderWorktreeExisting();
    }, "secondary");
    add.disabled = !editable;
    worktree.disabled = !editable;
    return listItem(workspace.name, state, open, add, worktree);
  }));
}

async function refreshWorktreeInventory(root: string): Promise<void> {
  if (!current) return;
  try {
    const response = await invoke<{ worktrees: Array<{ path: string; project: string; branch?: string; dirty: boolean }> }>("worktree_inventory", { enclave: enclaveInput(current), worktreesRoot: root });
    if (!response.worktrees.length) return;
    cleanupSuggestions.replaceChildren(...response.worktrees.map((worktree) => {
      const review = actionButton("Review", () => { cleanupPath.value = worktree.path; cleanupResult.textContent = `Selected ${worktree.project}${worktree.branch ? ` · ${worktree.branch}` : ""}.`; });
      const bindings = currentReport?.context.workspaces.flatMap((workspace) => workspace.projects.filter((project) => project.path === worktree.path).map(() => workspace.name)) ?? [];
      const actions: HTMLElement[] = [review];
      for (const workspace of bindings) {
        actions.push(actionButton(`Detach ${workspace}`, () => void reviewChange("detach", workspace, { name: worktree.project, path: worktree.path, kind: "git_worktree" })));
      }
      return el("div", { className: `cleanup-item ${bindings.length ? "bound" : "orphan"}` }, el("span", { textContent: `${worktree.project}${worktree.branch ? ` · ${worktree.branch}` : ""}${worktree.dirty ? " · uncommitted" : ""} · ${bindings.length ? bindings.join(", ") : "orphan"}` }), ...actions);
    }));
  } catch { /* The current context map remains usable if inventory is unavailable. */ }
}

function worktreeBindings(path: string): string[] {
  return currentReport?.context.workspaces.flatMap((workspace) => workspace.projects
    .filter((project) => project.path === path)
    .map(() => workspace.name)) ?? [];
}

const SYSTEM_SSH = "";
const INLINE_SSH = "__inline__";
const NEW_CREDENTIAL = "__new__";
let editingProfile: ConnectionProfile | undefined;
let editingCredential: Credential | undefined;
let returnToProfileForm = false;

/** randomUUID needs a secure context; the Tailscale UX preview is plain HTTP. */
function newId(): string {
  return crypto.randomUUID?.() ?? Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, props: Partial<HTMLElementTagNameMap[K]> = {}, ...children: (Node | string)[]): HTMLElementTagNameMap[K] {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
}

function showPane(name: string): void {
  const pane = document.querySelector<HTMLElement>(`[data-pane="${name}"]`);
  if (!pane) return;
  for (const sibling of pane.parentElement!.querySelectorAll<HTMLElement>(":scope > [data-pane]")) sibling.hidden = sibling !== pane;
  pane.querySelector<HTMLElement>("input:not([type=radio]):not([hidden])")?.focus();
}

function radioValue(name: string): string {
  return document.querySelector<HTMLInputElement>(`input[name="${name}"]:checked`)!.value;
}

function setRadio(name: string, value: string): void {
  for (const input of document.querySelectorAll<HTMLInputElement>(`input[name="${name}"]`)) input.checked = input.value === value;
}

function authLabel(authentication: SshAuthentication): string {
  return authentication.kind === "private_key" ? `Key file · ${authentication.path}` : authentication.kind === "password" ? "Password" : "SSH agent";
}

function profileUsers(credentialId: string): string[] {
  return profiles.filter((profile) => profile.credential_id === credentialId).map((profile) => profile.name);
}

function describeProfile(profile: ConnectionProfile): string {
  const credential = savedCredentials.find((item) => item.id === profile.credential_id);
  if (profile.target.kind !== "ssh") return describeTarget(profile.target);
  const user = profile.credential_id ? profile.ssh?.username : undefined;
  const signIn = credential ? credential.name : profile.ssh?.authentication.kind && profile.ssh.authentication.kind !== "agent" ? "saved in profile" : "system SSH";
  return `SSH · ${user ? `${user}@` : ""}${profile.target.destination} · ${signIn}`;
}

function emptyState(text: string, action: string, onClick: () => void): HTMLElement {
  const button = el("button", { type: "button", textContent: action });
  button.addEventListener("click", onClick);
  return el("div", { className: "empty-state" }, el("p", { textContent: text }), button);
}

function listItem(title: string, detail: string, ...actions: HTMLElement[]): HTMLElement {
  return el("div", { className: "list-item" }, el("div", {}, el("strong", { textContent: title }), el("span", { textContent: detail })), ...actions);
}

function actionButton(text: string, onClick: () => void, className = "secondary"): HTMLButtonElement {
  const button = el("button", { type: "button", className, textContent: text });
  button.addEventListener("click", onClick);
  return button;
}

// Credentials & keys

function refreshCredentialForm(): void {
  const kind = radioValue("credential-kind");
  keyPathField.hidden = kind !== "private_key";
  secretLabel.textContent = kind === "private_key" ? "Key passphrase" : "Password";
  const keepsSecret = editingCredential?.authentication.kind === kind && (kind === "password" || (editingCredential.authentication.kind === "private_key" && editingCredential.authentication.has_passphrase));
  secretHint.textContent = keepsSecret ? "Leave empty to keep the stored secret." : kind === "private_key" ? "Leave empty if the key has no passphrase. Stored in the operating-system vault." : "Stored in the operating-system vault, never in Studio files.";
}

function openCredentialForm(credential?: Credential, fromProfile = false): void {
  editingCredential = credential;
  returnToProfileForm = fromProfile;
  showView("credentials");
  credentialFormTitle.textContent = credential ? `Edit ${credential.name}` : "New credential";
  credentialName.value = credential?.name ?? "";
  setRadio("credential-kind", credential?.authentication.kind === "password" ? "password" : "private_key");
  keyPath.value = credential?.authentication.kind === "private_key" ? credential.authentication.path : "";
  secret.value = "";
  credentialResult.textContent = "";
  const users = credential ? profileUsers(credential.id) : [];
  credentialDelete.hidden = !credential;
  credentialDelete.disabled = users.length > 0;
  credentialDelete.title = users.length ? `Used by ${users.join(", ")}` : "";
  refreshCredentialForm();
  showPane("credential-form");
}

function leaveCredentialForm(selectId?: string): void {
  secret.value = "";
  if (returnToProfileForm) {
    returnToProfileForm = false;
    showView("profiles");
    renderCredentialOptions(selectId ?? SYSTEM_SSH);
    showPane("profile-form");
  } else showPane("credentials");
}

async function saveCredential(): Promise<void> {
  const name = credentialName.value.trim();
  const kind = radioValue("credential-kind");
  if (!name) { credentialResult.textContent = "Give the credential a name you will recognise, e.g. “Work laptop key”."; return; }
  const sameKind = editingCredential?.authentication.kind === kind;
  let authentication: SshAuthentication;
  if (kind === "private_key") {
    const path = keyPath.value.trim();
    if (!path) { credentialResult.textContent = "Enter the path to the private key file."; return; }
    const kept = sameKind && editingCredential?.authentication.kind === "private_key" && editingCredential.authentication.has_passphrase;
    authentication = { kind: "private_key", path, has_passphrase: secret.value.length > 0 || kept };
  } else {
    if (!secret.value && !sameKind) { credentialResult.textContent = "Enter the password."; return; }
    authentication = { kind: "password" };
  }
  const credential: Credential = { id: editingCredential?.id ?? newId(), name, authentication };
  credentialSave.disabled = true;
  try {
    await invoke("save_credential", { credential, secret: secret.value || null });
    await loadStore();
    result.textContent = `Credential “${name}” saved.`;
    leaveCredentialForm(credential.id);
  } catch (error) { credentialResult.textContent = `Could not save: ${String(error)}`; }
  finally { credentialSave.disabled = false; }
}

function renderCredentials(): void {
  credentialList.replaceChildren(...(savedCredentials.length ? savedCredentials.map((credential) => {
    const users = profileUsers(credential.id);
    return listItem(credential.name, `${authLabel(credential.authentication)} · ${users.length ? `used by ${users.join(", ")}` : "not used yet"}`, actionButton("Edit", () => openCredentialForm(credential)));
  }) : [emptyState("No credentials yet. You need one only when Studio itself signs in to a remote server with a key file or a password. This computer and WSL2 run Orcan directly as your user, and with an SSH agent your system ssh already holds the key, so none of those needs a credential here.", "Add a credential or key", () => openCredentialForm())]));
}

// Profiles

function renderCredentialOptions(selected: string): void {
  const options = [new Option("System SSH — SSH agent or ~/.ssh/config", SYSTEM_SSH), ...savedCredentials.map((item) => new Option(`${item.name} · ${authLabel(item.authentication)}`, item.id))];
  const inline = editingProfile?.target.kind === "ssh" && !editingProfile.credential_id && editingProfile.ssh && editingProfile.ssh.authentication.kind !== "agent";
  if (inline) options.push(new Option("Saved in this profile (older format)", INLINE_SSH));
  options.push(new Option("＋ Add a credential or key…", NEW_CREDENTIAL));
  credentialSelect.replaceChildren(...options);
  credentialSelect.value = options.some((option) => option.value === selected) ? selected : SYSTEM_SSH;
  refreshProfileForm();
}

function refreshProfileForm(): void {
  const location = radioValue("location");
  wslFields.hidden = location !== "wsl2";
  sshFields.hidden = location !== "ssh";
  const value = credentialSelect.value;
  credentialHint.textContent = value === SYSTEM_SSH
    ? "Signs in like ssh in a terminal: your SSH agent and ~/.ssh/config. For a custom port, add a Host alias there."
    : value === INLINE_SSH ? "Kept as saved. Choose a shared credential to reuse it across profiles."
    : "Studio signs in natively with this credential; the user field is required.";
  profileTestResult.textContent = "";
  profileTestHint.hidden = true;
}

function openProfileForm(profile?: ConnectionProfile): void {
  editingProfile = profile;
  showView("profiles");
  profileFormTitle.textContent = profile ? `Edit ${profile.name}` : "New profile";
  profileName.value = profile?.name ?? "";
  setRadio("location", profile?.target.kind ?? "ssh");
  wslDistribution.value = profile?.target.kind === "wsl2" ? profile.target.distribution : "Ubuntu-24.04";
  let host = profile?.target.kind === "ssh" ? profile.target.destination : "";
  let user = profile?.ssh?.username ?? "";
  if (profile?.target.kind === "ssh" && !profile.credential_id && host.includes("@")) {
    user = host.slice(0, host.lastIndexOf("@"));
    host = host.slice(host.lastIndexOf("@") + 1);
  }
  sshHost.value = host;
  sshUser.value = user;
  profileDelete.hidden = !profile;
  renderCredentialOptions(profile?.credential_id ?? (profile?.ssh && profile.ssh.authentication.kind !== "agent" ? INLINE_SSH : SYSTEM_SSH));
  showPane("profile-form");
}

/** Builds the profile and the connection that tests it, from the form. */
function profileFromForm(): { profile: ConnectionProfile; connection: Connection } {
  const name = profileName.value.trim();
  const location = radioValue("location");
  const id = editingProfile?.id ?? newId();
  if (location === "local") return { profile: { id, name, target: { kind: "local" } }, connection: { target: { kind: "local" }, label: name || "This computer" } };
  if (location === "wsl2") {
    const distribution = wslDistribution.value.trim();
    if (!distribution) throw new Error("Enter the WSL2 distribution name.");
    const target: Target = { kind: "wsl2", distribution };
    return { profile: { id, name, target }, connection: { target, label: name || `WSL2 ${distribution}` } };
  }
  const host = sshHost.value.trim();
  const user = sshUser.value.trim();
  if (!host) throw new Error("Enter the server address.");
  if (/\s/.test(host) || /\s/.test(user)) throw new Error("The address and user cannot contain spaces.");
  const choice = credentialSelect.value;
  const label = name || `${user ? `${user}@` : ""}${host}`;
  if (choice === SYSTEM_SSH) {
    const target: Target = { kind: "ssh", destination: user ? `${user}@${host}` : host };
    return { profile: { id, name, target }, connection: { target, label } };
  }
  const target: Target = { kind: "ssh", destination: host };
  if (choice === INLINE_SSH && editingProfile) {
    return { profile: { id, name, target, ssh: { ...editingProfile.ssh!, username: user || undefined } }, connection: { target, label, profileId: editingProfile.id } };
  }
  if (!user) throw new Error("Enter the user on the server; a saved credential proves who you are, but not which account.");
  return {
    profile: { id, name, target, ssh: { username: user, authentication: { kind: "agent" } }, credential_id: choice },
    connection: { target, label, credentialId: choice, username: user },
  };
}

async function testProfile(): Promise<void> {
  profileTestHint.hidden = true;
  let connection: Connection;
  try { connection = profileFromForm().connection; }
  catch (error) { profileTestResult.textContent = error instanceof Error ? error.message : String(error); return; }
  profileTest.disabled = true;
  profileTestResult.textContent = `Testing ${connection.label}: connecting → asking Orcan for its report…`;
  try {
    const report = await invoke<ProbeReport>("probe", { enclave: enclaveInput(connection) });
    const agents = Object.entries(report.runtime.docker.agents ?? {}).filter(([, available]) => available).map(([name]) => name);
    profileTestResult.textContent = `✓ Reached Orcan ${report.sandbox.version} on ${report.host.os} · container ${report.runtime.docker.container.state} · ${report.context.workspaces.length} workspace families${agents.length ? ` · agents: ${agents.join(", ")}` : ""}`;
  } catch (error) {
    profileTestResult.textContent = `✕ ${String(error)}`;
    profileTestHint.textContent = failureHint(String(error));
    profileTestHint.hidden = false;
  } finally { profileTest.disabled = false; }
}

async function saveProfile(): Promise<void> {
  let built: ReturnType<typeof profileFromForm>;
  try { built = profileFromForm(); }
  catch (error) { profileTestResult.textContent = error instanceof Error ? error.message : String(error); return; }
  if (!built.profile.name) { profileTestResult.textContent = "Give the profile a name, e.g. “Build server”."; profileName.focus(); return; }
  profileSave.disabled = true;
  try {
    await invoke("save_profile", { profile: built.profile });
    if (current?.profileId === built.profile.id) lockStudio();
    enclaveStatus.delete(built.profile.id);
    await loadStore();
    void checkEnclave(built.profile);
    result.textContent = `Profile “${built.profile.name}” saved. Connect its Enclave below.`;
    showPane("profiles");
    showView("enclaves");
  } catch (error) { profileTestResult.textContent = `Could not save: ${String(error)}`; }
  finally { profileSave.disabled = false; }
}

function renderProfiles(): void {
  profileList.replaceChildren(...(profiles.length ? profiles.map((profile) => listItem(profile.name, describeProfile(profile), actionButton("Edit", () => openProfileForm(profile))))
    : [emptyState("No profiles yet. A profile says where Orcan runs and how Studio signs in.", "Create a profile", () => openProfileForm())]));
}

// Enclaves

type EnclaveStatus = { state: "checking" | "online" | "offline"; report?: ProbeReport; error?: string; at?: number };
const enclaveStatus = new Map<string, EnclaveStatus>();
const enclaveChecks = new Map<string, Promise<EnclaveStatus>>();
const navEnclaves = $("#nav-enclaves");
let lastCheckAll = 0;

function profileConnection(profile: ConnectionProfile): Connection {
  return { target: profile.target, label: profile.name, profileId: profile.id };
}

/** online = container running, warn = Orcan reachable but container not running. */
function statusTone(status?: EnclaveStatus): string {
  if (!status) return "idle";
  if (status.state !== "online") return status.state;
  return status.report?.runtime.docker.container.state === "running" ? "online" : "warn";
}

function ago(at?: number): string {
  const seconds = Math.round((Date.now() - (at ?? Date.now())) / 1000);
  return seconds < 45 ? "just now" : seconds < 3600 ? `${Math.round(seconds / 60)} min ago` : `${Math.round(seconds / 3600)} h ago`;
}

function statusText(status?: EnclaveStatus): string {
  if (!status) return "Not checked yet";
  if (status.state === "checking") return status.report ? `Checking… (last: container ${status.report.runtime.docker.container.state})` : "Checking…";
  if (status.state === "offline") return `Unreachable · checked ${ago(status.at)}`;
  return `Orcan ${status.report!.sandbox.version} · container ${status.report!.runtime.docker.container.state} · checked ${ago(status.at)}`;
}

function dot(tone: string): HTMLElement {
  return el("span", { className: `state-dot ${tone}` });
}

async function checkEnclaveNow(profile: ConnectionProfile): Promise<EnclaveStatus> {
  enclaveStatus.set(profile.id, { ...enclaveStatus.get(profile.id), state: "checking" });
  renderEnclaveStatus();
  let status: EnclaveStatus;
  try {
    const report = await invoke<ProbeReport>("probe", { enclave: enclaveInput(profileConnection(profile)) });
    localStorage.setItem(cacheKey(profile.target), JSON.stringify(report));
    status = { state: "online", report, at: Date.now() };
  } catch (error) {
    status = {
      state: "offline",
      report: enclaveStatus.get(profile.id)?.report,
      error: String(error),
      at: Date.now(),
    };
  }
  enclaveStatus.set(profile.id, status);
  if (connected && current?.profileId === profile.id) {
    if (status.report) renderSnapshot(status.report);
    else lockStudio();
  }
  renderEnclaveStatus();
  return status;
}

function checkEnclave(profile: ConnectionProfile): Promise<EnclaveStatus> {
  const inFlight = enclaveChecks.get(profile.id);
  if (inFlight) return inFlight;
  const pending = checkEnclaveNow(profile).finally(() => enclaveChecks.delete(profile.id));
  enclaveChecks.set(profile.id, pending);
  return pending;
}

/** Checks every saved Enclave, at most once a minute unless forced. */
function checkAll(force = false): void {
  if (!force && Date.now() - lastCheckAll < 60_000) return;
  lastCheckAll = Date.now();
  for (const profile of profiles) void checkEnclave(profile);
}

function activate(connection: Connection, report: ProbeReport): void {
  if (current?.profileId !== connection.profileId) syncBanner.hidden = true;
  current = connection;
  renderSnapshot(report);
  renderChangeSet();
  activeGroup.textContent = `ACTIVE · ${connection.label.toUpperCase()}`;
  renderStore();
}

function cachedEnclaveReport(profile: ConnectionProfile): ProbeReport | undefined {
  try {
    const raw = localStorage.getItem(cacheKey(profile.target));
    return raw ? JSON.parse(raw) as ProbeReport : undefined;
  } catch {
    return undefined;
  }
}

/** Makes an Enclave active immediately, then verifies it in the background. */
async function openEnclave(profile: ConnectionProfile): Promise<void> {
  const connection = profileConnection(profile);
  const report = enclaveStatus.get(profile.id)?.report ?? cachedEnclaveReport(profile);
  if (report) {
    if (!enclaveStatus.get(profile.id)?.report) {
      enclaveStatus.set(profile.id, { state: "online", report, at: Date.now() });
    }
    activate(connection, report);
    showView("overview");
    void checkEnclave(profile);
    return;
  }
  result.textContent = `Connecting to ${profile.name}…`;
  showView("enclaves");
  const status = await checkEnclave(profile);
  if (status.report) {
    activate(connection, status.report);
    showView("overview");
  }
}

function renderEnclaves(): void {
  enclaveList.replaceChildren(...(profiles.length ? profiles.map((profile) => {
    const status = enclaveStatus.get(profile.id);
    const drafts = queuedChanges.filter((change) => change.enclave === enclaveChangeKey(profileConnection(profile))).length;
    const active = connected && current?.profileId === profile.id;
    const actions: HTMLElement[] = [actionButton("Check", () => void checkEnclave(profile))];
    if (active) actions.push(el("span", { className: "badge", textContent: "Active" }));
    else actions.push(actionButton("Open", () => void openEnclave(profile), status?.state === "online" ? "" : "secondary"));
    const access = status?.report ? ` · ${accessExposure(status.report.runtime.launch)}` : "";
    const text = el("div", {}, el("strong", {}, dot(statusTone(status)), profile.name), el("span", { textContent: `${describeProfile(profile)} · ${statusText(status)}${access}${drafts ? ` · ${drafts} draft${drafts === 1 ? "" : "s"}` : ""}` }));
    if (status?.state === "offline") text.append(el("span", { className: "status-hint", textContent: failureHint(status.error ?? "") }));
    const item = el("div", { className: "list-item enclave-item" }, text, el("div", { className: "item-actions" }, ...actions));
    item.classList.toggle("active", active);
    return item;
  }) : [emptyState("Enclaves appear here once you create a profile.", "Create a profile", () => openProfileForm())]));
}

/** Per-Enclave state everywhere it is shown: list, sidebar, topbar chip, summary. */
function renderEnclaveStatus(): void {
  renderEnclaves();
  navEnclaves.replaceChildren(...profiles.map((profile) => {
    const drafts = queuedChanges.filter((change) => change.enclave === enclaveChangeKey(profileConnection(profile))).length;
    const button = el("button", { type: "button", className: "nav-enclave", title: `${statusText(enclaveStatus.get(profile.id))}${drafts ? ` · ${drafts} drafts` : ""}` }, dot(statusTone(enclaveStatus.get(profile.id))), el("span", { textContent: profile.name }), ...(drafts ? [el("small", { className: "draft-count", textContent: String(drafts) })] : []));
    button.classList.toggle("active", connected && current?.profileId === profile.id);
    button.addEventListener("click", () => void openEnclave(profile));
    return button;
  }));
  const activeStatus = current?.profileId ? enclaveStatus.get(current.profileId) : undefined;
  activeDot.className = `state-dot ${connected ? statusTone(activeStatus) : "idle"}`;
  activeLabel.textContent = connected && current ? `${current.label} · ${activeStatus?.report?.runtime.docker.container.state ?? "connected"}` : profiles.length ? "Choose an Enclave" : "No Enclaves yet";
  const online = profiles.filter((profile) => enclaveStatus.get(profile.id)?.state === "online").length;
  const checking = profiles.some((profile) => enclaveStatus.get(profile.id)?.state === "checking");
  instanceState.textContent = profiles.length ? `${online} of ${profiles.length} Enclave${profiles.length === 1 ? "" : "s"} online${checking ? " · checking…" : ""}` : "No Enclaves yet";
}

function failureHint(error: string): string {
  if (/host-key|known_hosts|Host key verification/i.test(error)) return "The server's host key is not trusted yet. Connect once from a terminal (ssh <server>) to confirm its fingerprint, then test again.";
  if (/authentication|Permission denied|rejected/i.test(error)) return "The server rejected the sign-in. Check the user and the credential.";
  if (/no (password|key-passphrase) is stored/i.test(error)) return "The secret for this credential is missing from the vault. Edit the credential and enter it again.";
  if (/command not found|No such file|orcan: not found/i.test(error)) return "The machine was reached, but Orcan is not installed there or not on PATH.";
  if (/timed out|Connection refused|resolve|unreachable/i.test(error)) return "The machine could not be reached. Check the address, port, VPN, or Tailscale.";
  return "Adjust the details and test again; the Activity view keeps the full error.";
}

function renderSetup(): void {
  setupPanel.hidden = connected;
  $("#setup-credential").classList.toggle("done", savedCredentials.length > 0 || profiles.length > 0);
  $("#setup-profile").classList.toggle("done", profiles.length > 0);
  $("#setup-enclave").classList.toggle("done", connected);
}

function renderStore(): void {
  renderCredentials();
  renderProfiles();
  renderEnclaveStatus();
  renderSetup();
}

async function loadStore(): Promise<void> {
  [profiles, savedCredentials] = await Promise.all([invoke<ConnectionProfile[]>("list_profiles"), invoke<Credential[]>("list_credentials")]);
  renderStore();
}

/** Probes an Enclave and, on success, makes it the active one. */
async function connect(connection: Connection, output: HTMLOutputElement = result): Promise<ProbeReport | undefined> {
  const request = ++latestProbe;
  output.textContent = `Connecting to ${connection.label} → reading Orcan report → checking runtime…`;
  const job = addJob("Enclave check", connection.label);
  try {
    const report = await invoke<ProbeReport>("probe", { enclave: enclaveInput(connection) });
    if (request !== latestProbe) return undefined;
    localStorage.setItem(cacheKey(connection.target), JSON.stringify(report));
    if (connection.profileId) enclaveStatus.set(connection.profileId, { state: "online", report, at: Date.now() });
    activate(connection, report);
    output.textContent = `Connected · ${report.host.os}/${report.host.architecture} · Orcan ${report.sandbox.version} · container ${report.runtime.docker.container.state}`;
    finishJob(job, "succeeded", "Enclave report refreshed");
    renderStore();
    return report;
  } catch (error) {
    if (request !== latestProbe) return undefined;
    if (connection.profileId) enclaveStatus.set(connection.profileId, { state: "offline", error: String(error), at: Date.now() });
    lockStudio();
    output.textContent = `Connection failed: ${String(error)}`;
    finishJob(job, "failed", String(error));
    renderStore();
    throw error;
  }
}

for (const button of document.querySelectorAll<HTMLButtonElement>("[data-go]")) button.addEventListener("click", () => showView(button.dataset.go!));
for (const button of document.querySelectorAll<HTMLButtonElement>("[data-pane-target]")) button.addEventListener("click", () => showPane(button.dataset.paneTarget!));
$("#new-profile").addEventListener("click", () => openProfileForm());
$("#new-credential").addEventListener("click", () => openCredentialForm());
$("#credential-back").addEventListener("click", () => leaveCredentialForm());
for (const input of document.querySelectorAll<HTMLInputElement>('input[name="location"]')) input.addEventListener("change", refreshProfileForm);
for (const input of document.querySelectorAll<HTMLInputElement>('input[name="credential-kind"]')) input.addEventListener("change", refreshCredentialForm);
credentialSelect.addEventListener("change", () => {
  if (credentialSelect.value === NEW_CREDENTIAL) { openCredentialForm(undefined, true); return; }
  refreshProfileForm();
});
profileTest.addEventListener("click", () => void testProfile());
profileSave.addEventListener("click", () => void saveProfile());
profileDelete.addEventListener("click", async () => {
  if (!editingProfile || !window.confirm(`Delete the profile ${editingProfile.name}? Nothing changes on the machine.`)) return;
  await invoke("delete_profile", { id: editingProfile.id });
  if (current?.profileId === editingProfile.id) lockStudio();
  await loadStore();
  showPane("profiles");
});
credentialSave.addEventListener("click", () => void saveCredential());
credentialDelete.addEventListener("click", async () => {
  if (!editingCredential || !window.confirm(`Delete the credential ${editingCredential.name}? Its secret is removed from the vault.`)) return;
  try { await invoke("delete_credential", { id: editingCredential.id }); await loadStore(); leaveCredentialForm(); }
  catch (error) { credentialResult.textContent = `Could not delete: ${String(error)}`; }
});
for (const item of navigationItems) item.addEventListener("click", () => showView(item.dataset.viewTarget ?? "overview"));
settingsRefresh.addEventListener("click", () => { if (current) void connect(current, settingsResult).catch(() => undefined); });
for (const [action, selector] of Object.entries(runtimeButtons)) document.querySelector<HTMLButtonElement>(selector)!.addEventListener("click", () => void runRuntimeAction(action as RuntimeAction));
settingsSync.addEventListener("click", async () => { if (!current || !canEditContext()) { settingsResult.textContent = contextEditMessage(); return; } const job = addJob("Orcan sync", current.label); settingsSync.disabled = true; settingsResult.textContent = "Reconciling Orcan context…"; try { await invoke("sync", { enclave: enclaveInput(current) }); settingsResult.textContent = "Sync completed. Restart is required only if Orcan reports a Compose-level change."; finishJob(job, "succeeded", "Context reconciled"); } catch (error) { settingsResult.textContent = `Sync failed: ${String(error)}`; finishJob(job, "failed", String(error)); } finally { settingsSync.disabled = false; } });
worktreeRepo.addEventListener("change", renderWorktreeExisting);
worktreeWorkspaces.addEventListener("change", renderWorktreeExisting);
worktreePlan.addEventListener("click", async () => {
  if (!current) return;
  if (!canEditContext()) { worktreeResult.textContent = contextEditMessage(); return; }
  const workspaces = selectedWorkspaces();
  if (!worktreeRepo.value || !workspaces.length) {
    worktreeResult.textContent = "Choose a Git source and at least one workspace family.";
    return;
  }
  try {
    const response = await invoke<{ plan: { project?: string; destination: string; ready: boolean; blockers: string[] } }>("worktree_plan", { enclave: enclaveInput(current), repo: worktreeRepo.value, branch: worktreeBranch.value, worktreesRoot: setting("setting-worktrees-root").textContent, workspaces });
    worktreeReady = response.plan.ready;
    worktreeApply.disabled = !worktreeReady;
    worktreeResult.textContent = response.plan.ready
      ? `Ready: ${response.plan.project ?? "worktree"} → ${response.plan.destination} · attach to ${workspaces.join(", ")}.`
      : response.plan.blockers.join(" · ");
  } catch (error) {
    worktreeReady = false;
    worktreeApply.disabled = true;
    worktreeResult.textContent = `Plan failed: ${String(error)}`;
  }
});
worktreeApply.addEventListener("click", async () => {
  if (!worktreeReady || !current) return;
  if (!canEditContext()) { worktreeResult.textContent = contextEditMessage(); return; }
  const workspaces = selectedWorkspaces();
  worktreeApply.disabled = true;
  worktreeResult.textContent = "Creating worktree…";
  const job = addJob("Worktree create", worktreeBranch.value);
  try {
    const response = await invoke<{ result: { path: string } }>("worktree_apply", { enclave: enclaveInput(current), repo: worktreeRepo.value, branch: worktreeBranch.value, worktreesRoot: setting("setting-worktrees-root").textContent, workspaces });
    worktreeReady = false;
    await connect(current);
    worktreeResult.textContent = `Created: ${response.result.path}. Map refreshed; run Orcan sync when you want the Enclave mounts reconciled.`;
    finishJob(job, "succeeded", response.result.path);
  } catch (error) {
    worktreeResult.textContent = `Create failed: ${String(error)}`;
    finishJob(job, "failed", String(error));
  }
});
function resetCleanupPlan(): void {
  cleanupReady = false;
  cleanupApply.disabled = true;
}

cleanupPath.addEventListener("input", resetCleanupPlan);
cleanupRemoveBranch.addEventListener("change", resetCleanupPlan);
cleanupPlan.addEventListener("click", async () => {
  if (!current) return;
  if (!canEditContext()) { cleanupResult.textContent = contextEditMessage(); return; }
  const bindings = worktreeBindings(cleanupPath.value);
  if (bindings.length) {
    resetCleanupPlan();
    cleanupResult.textContent = `Detach this worktree from ${bindings.join(", ")} before deleting its directory.`;
    return;
  }
  try {
    const response = await invoke<{ plan: { branch?: string; ready: boolean; blockers: string[] } }>("worktree_cleanup", { enclave: enclaveInput(current), path: cleanupPath.value, worktreesRoot: setting("setting-worktrees-root").textContent, removeBranch: cleanupRemoveBranch.checked, apply: false });
    cleanupReady = response.plan.ready;
    cleanupApply.disabled = !cleanupReady || cleanupConfirm.value !== "REMOVE";
    cleanupResult.textContent = response.plan.ready
      ? `Ready to remove ${response.plan.branch ?? "the worktree"}${cleanupRemoveBranch.checked ? " and its merged branch" : ""}. Type REMOVE to enable deletion.`
      : response.plan.blockers.join(" · ");
  } catch (error) {
    resetCleanupPlan();
    cleanupResult.textContent = `Plan failed: ${String(error)}`;
  }
});
cleanupConfirm.addEventListener("input", () => { cleanupApply.disabled = !cleanupReady || cleanupConfirm.value !== "REMOVE"; });
cleanupApply.addEventListener("click", async () => {
  if (!current || !cleanupReady || cleanupConfirm.value !== "REMOVE") return;
  if (!canEditContext()) { cleanupResult.textContent = contextEditMessage(); return; }
  const connection = current;
  const path = cleanupPath.value;
  const job = addJob("Worktree cleanup", path);
  try {
    await invoke("worktree_cleanup", { enclave: enclaveInput(connection), path, worktreesRoot: setting("setting-worktrees-root").textContent, removeBranch: cleanupRemoveBranch.checked, apply: true });
    await connect(connection);
    cleanupResult.textContent = "Worktree removed and Studio refreshed the context map.";
    resetCleanupPlan();
    cleanupConfirm.value = "";
    finishJob(job, "succeeded", path);
  } catch (error) {
    cleanupResult.textContent = `Removal failed: ${String(error)}`;
    finishJob(job, "failed", String(error));
  }
});
importPlanButton.addEventListener("click", async () => {
  if (!current || !latestProbe || !snapshotRoot.textContent || snapshotRoot.textContent === "—") { importResult.textContent = "Check an Enclave first."; return; }
  importPlanButton.disabled = true; importResult.textContent = "Building import plan…";
  try {
    const response = await invoke<{ plan: { destination: string; destination_state: string; ready: boolean; blockers: string[] } }>("import_plan", { enclave: enclaveInput(current), source: importSource.value, projectsRoot: snapshotRoot.textContent, destination: importDestination.value || undefined });
    importReady = response.plan.ready; importApplyButton.disabled = !importReady;
    importResult.textContent = response.plan.ready ? `Ready: ${response.plan.destination} · ${response.plan.destination_state}` : response.plan.blockers.join(" · ");
  } catch (error) { importReady = false; importApplyButton.disabled = true; importResult.textContent = `Plan failed: ${String(error)}`; }
  finally { importPlanButton.disabled = false; }
});
importApplyButton.addEventListener("click", async () => {
  if (!importReady) return;
  importApplyButton.disabled = true; importResult.textContent = "Cloning repository…";
  const job = addJob("Repository import", importSource.value);
  try { const response = await invoke<{ result: { destination: string } }>("import_apply", { enclave: enclaveInput(current!), source: importSource.value, projectsRoot: snapshotRoot.textContent, destination: importDestination.value || undefined }); importResult.textContent = `Imported: ${response.result.destination}`; importReady = false; finishJob(job, "succeeded", response.result.destination); }
  catch (error) { importResult.textContent = `Import failed: ${String(error)}`; finishJob(job, "failed", String(error)); }
});
parentRepository.addEventListener("change", () => {
  if (parentRepository.value === "__manual__") {
    parentPath.hidden = false;
    parentPath.value = "";
    parentPath.focus();
  } else {
    const candidate = currentReport && parentCandidates(currentReport).find((item) => item.path === parentRepository.value);
    parentPath.hidden = true;
    parentPath.value = parentRepository.value;
    if (candidate?.branch) parentBranch.value = candidate.branch;
  }
  parentHead = undefined;
  parentApplyButton.disabled = true;
  parentResult.textContent = "Preview before applying an update.";
});
parentPlanButton.addEventListener("click", async () => {
  parentPlanButton.disabled = true; parentResult.textContent = "Checking parent repository…";
  try {
    if (!current) return;
    const response = await invoke<{ plan: { head: string; ready: boolean; blockers: string[] } }>("parent_plan", { enclave: enclaveInput(current), path: parentPath.value, branch: parentBranch.value });
    parentHead = response.plan.head;
    parentApplyButton.disabled = !response.plan.ready;
    parentResult.textContent = response.plan.ready ? `Ready to fast-forward from ${parentHead}.` : response.plan.blockers.join(" · ");
  } catch (error) { parentHead = undefined; parentApplyButton.disabled = true; parentResult.textContent = `Plan failed: ${String(error)}`; }
  finally { parentPlanButton.disabled = false; }
});
parentApplyButton.addEventListener("click", async () => {
  if (!parentHead) return;
  parentApplyButton.disabled = true; parentResult.textContent = "Applying approved fast-forward…";
  const job = addJob("Parent update", parentBranch.value);
  try {
    await invoke("parent_apply", { enclave: enclaveInput(current!), path: parentPath.value, branch: parentBranch.value, expectedHead: parentHead });
    rememberParentRun(parentPath.value, parentBranch.value);
    if (currentReport) renderParentRepositories(currentReport);
    parentResult.textContent = "Parent updated.";
    finishJob(job, "succeeded", "Fast-forward applied");
  }
  catch (error) { parentResult.textContent = `Update failed: ${String(error)}`; finishJob(job, "failed", String(error)); }
  finally { parentApplyButton.disabled = false; }
});

renderJobs();
if (demoMode) {
  demoBanner.hidden = false;
  result.textContent = "UX preview: every action below uses sample data.";
  void previewSnapshot.then((snapshot) => {
    if (snapshot) demoBanner.textContent = `UX preview · “Demo workstation” shows a read-only snapshot of this host (${snapshot.context.workspaces.map((workspace) => workspace.name).join(", ") || "no workspaces"}); other Enclaves and all actions use sample data.`;
  });
}
activeInstance.addEventListener("click", () => showView("enclaves"));
void loadStore().then(() => checkAll(true)).catch((error) => {
  result.textContent = `Could not load saved Enclaves: ${String(error)}`;
});
