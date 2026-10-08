import { actionButton, el, emptyState, listItem, radioValue, setRadio } from "./dom";
import { loadJobs, persistJobs, type Job } from "./activity";
import { draftConflicts, loadQueuedChanges, persistQueuedChanges, type QueuedChange } from "./context-drafts";
import { parentCandidates, parentDirectory, parentForProject, parentLabel, parseDraggedProject, projectAlerts, projectGroup, projectName, unassignedProjects, type ContextProject, type HealthProject, type ParentCandidate } from "./context-model";
import { loadParentRuns, rememberParentRun } from "./parent-runs";
import { loadMapState, persistMapState, type MapFilter } from "./map-state";
import { normalizeProbeReport } from "./probe";
import { loadCachedReport, persistCachedReport } from "./report-cache";
import { cacheKey, demoMode, describeTarget, enclaveInput, invokeTauri } from "./transport";
import type { Connection, ConnectionProfile, Credential, MembershipArgs, ProbeReport, ProjectRef, SshAuthentication, SshHostKeyOffer, Target } from "./types";
import "./style.css";

const result = document.querySelector<HTMLOutputElement>("#result")!;
const $ = <T extends HTMLElement>(selector: string) => document.querySelector<T>(selector)!;
const profileList = $("#profile-list");
const enclaveList = $("#enclave-list");
const imageTransferSource = $<HTMLSelectElement>("#image-transfer-source");
const imageTransferName = $<HTMLInputElement>("#image-transfer-name");
const imageTransferTarget = $<HTMLSelectElement>("#image-transfer-target");
const imageTransferInspect = $<HTMLButtonElement>("#image-transfer-inspect");
const imageTransferRun = $<HTMLButtonElement>("#image-transfer-run");
const imageTransferResult = $<HTMLOutputElement>("#image-transfer-result");
const cliProvisionSource = $<HTMLSelectElement>("#cli-provision-source");
const cliProvisionTarget = $<HTMLSelectElement>("#cli-provision-target");
const cliProvisionImage = $<HTMLInputElement>("#cli-provision-image");
const cliProvisionImageField = $("#cli-provision-image-field");
const cliProvisionImageName = $<HTMLInputElement>("#cli-provision-image-name");
const cliProvisionCheck = $<HTMLButtonElement>("#cli-provision-check");
const cliProvisionRun = $<HTMLButtonElement>("#cli-provision-run");
const cliProvisionResult = $<HTMLOutputElement>("#cli-provision-result");
const onlineProvisionTarget = $<HTMLSelectElement>("#online-provision-target");
const onlineProvisionCheck = $<HTMLButtonElement>("#online-provision-check");
const onlineProvisionRun = $<HTMLButtonElement>("#online-provision-run");
const onlineProvisionResult = $<HTMLOutputElement>("#online-provision-result");
const enclaveCreateProfile = $<HTMLSelectElement>("#enclave-create-profile");
const enclaveCreateGit = $<HTMLInputElement>("#enclave-create-git");
const enclaveCreateDocker = $<HTMLInputElement>("#enclave-create-docker");
const enclaveCreateTtyd = $<HTMLInputElement>("#enclave-create-ttyd");
const enclaveCreateTtydAuth = $<HTMLInputElement>("#enclave-create-ttyd-auth");
const enclaveCreateTtydFields = $("#enclave-create-ttyd-fields");
const enclaveCreateTtydUser = $<HTMLInputElement>("#enclave-create-ttyd-user");
const enclaveCreateTtydPassword = $<HTMLInputElement>("#enclave-create-ttyd-password");
const enclaveCreatePlan = $<HTMLButtonElement>("#enclave-create-plan");
const enclaveCreateApply = $<HTMLButtonElement>("#enclave-create-apply");
const enclaveCreateResult = $<HTMLOutputElement>("#enclave-create-result");
const credentialList = $("#credential-list");
const setupPanel = $("#setup-panel");
const activeGroup = $("#active-group");
const profileFormTitle = $("#profile-form-title");
const profileName = $<HTMLInputElement>("#profile-name");
const wslFields = $("#wsl-fields");
const wslDistribution = $<HTMLSelectElement>("#wsl-distribution");
const wslDistributionHint = $("#wsl-distribution-hint");
const sshFields = $("#ssh-fields");
const sshSystemUserField = $("#ssh-system-user-field");
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
const credentialUser = $<HTMLInputElement>("#credential-user");
const keyPathField = $("#key-path-field");
const keyPath = $<HTMLInputElement>("#key-path");
const secret = $<HTMLInputElement>("#secret");
const secretLabel = $<HTMLLabelElement>("#secret-label");
const secretHint = $("#secret-hint");
const credentialResult = $<HTMLOutputElement>("#credential-result");
const credentialSave = $<HTMLButtonElement>("#credential-save");
const snapshot = document.querySelector<HTMLElement>("#snapshot")!;
const snapshotRoot = document.querySelector<HTMLElement>("#snapshot-root")!;
const snapshotWorkspaces = document.querySelector<HTMLElement>("#snapshot-workspaces")!;
const snapshotProjects = document.querySelector<HTMLElement>("#snapshot-projects")!;
const snapshotList = document.querySelector<HTMLElement>("#snapshot-list")!;
const sandboxPath = $("#sandbox-path");
const sandboxProjects = $("#sandbox-projects");
const sandboxRefresh = $<HTMLButtonElement>("#sandbox-refresh");
const sandboxResult = $<HTMLOutputElement>("#sandbox-result");
const contextManager = el("div", { className: "context-manager" });
const contextWorkspaceList = el("div", { className: "context-workspace-list" });
const contextWorkspaceDetail = el("section", { className: "context-workspace-detail" });
const contextWorkspaceNotice = el("output", { className: "context-workspace-notice", ariaLive: "polite" });
contextManager.append(contextWorkspaceList, contextWorkspaceDetail);
snapshot.insertBefore(contextManager, snapshotList);
const contextMap = document.querySelector<HTMLElement>("#context-map")!;
const parentRuns = loadParentRuns();

const importSource = document.querySelector<HTMLInputElement>("#import-source")!;
importSource.placeholder = "repository-url";
const importParent = document.querySelector<HTMLSelectElement>("#import-parent")!;
const importDestination = document.querySelector<HTMLElement>("#import-destination")!;
const importAuth = document.querySelector<HTMLElement>("#import-auth")!;
const importPlanButton = document.querySelector<HTMLButtonElement>("#import-plan")!;
const importApplyButton = document.querySelector<HTMLButtonElement>("#import-apply")!;
const importResult = document.querySelector<HTMLOutputElement>("#import-result")!;
const folderName = document.querySelector<HTMLInputElement>("#folder-name")!;
const folderPlanButton = document.querySelector<HTMLButtonElement>("#folder-plan")!;
const folderApplyButton = document.querySelector<HTMLButtonElement>("#folder-apply")!;
const folderResult = document.querySelector<HTMLOutputElement>("#folder-result")!;
let importReady = false;
let folderReady = false;
const sandboxSettings = document.querySelector<HTMLElement>("#sandbox-settings")!;
const connectionDoctor = document.createElement("section");
connectionDoctor.className = "connection-doctor";
sandboxSettings.prepend(connectionDoctor);
const settingsResult = document.querySelector<HTMLOutputElement>("#settings-result")!;
const settingsRefresh = document.querySelector<HTMLButtonElement>("#settings-refresh")!;
const settingsSync = document.querySelector<HTMLButtonElement>("#settings-sync")!;
const enclaveConfigOptions = document.querySelector<HTMLElement>("#enclave-config-options")!;
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
const setting = (id: string) => document.querySelector<HTMLElement>(`#${id}`)!;
const cleanupSuggestions = $("#cleanup-suggestions");
const cleanupResult = document.querySelector<HTMLOutputElement>("#cleanup-result")!;
const worktreeRepo = document.querySelector<HTMLSelectElement>("#worktree-repo")!;
const worktreeBranch = document.querySelector<HTMLInputElement>("#worktree-branch")!;
worktreeBranch.placeholder = "branch-name";
document.querySelector<HTMLLabelElement>('label[for="worktree-branch"]')!.textContent = "Branch to use";
const worktreeBranchState = document.createElement("p");
worktreeBranchState.className = "hint worktree-branch-state";
worktreeBranch.after(worktreeBranchState);
const worktreeWorkspaces = document.querySelector<HTMLSelectElement>("#worktree-workspaces")!;
const worktreePlan = document.querySelector<HTMLButtonElement>("#worktree-plan")!;
const worktreeApply = document.querySelector<HTMLButtonElement>("#worktree-apply")!;
const worktreeResult = document.querySelector<HTMLOutputElement>("#worktree-result")!;
const worktreeExisting = document.querySelector<HTMLElement>("#worktree-existing")!;
const branchBrowser = document.createElement("details");
branchBrowser.className = "branch-browser";
const branchSummary = document.createElement("summary");
const branchSearch = document.createElement("input");
branchSearch.placeholder = "filter branches";
const branchList = document.createElement("div");
branchList.className = "branch-list";
branchBrowser.append(branchSummary, branchSearch, branchList);
worktreeExisting.after(branchBrowser);
const worktreeSourceState = document.querySelector<HTMLElement>("#worktree-source-state")!;
const worktreeSourceUpdate = document.querySelector<HTMLButtonElement>("#worktree-source-update")!;
const jobsList = document.querySelector<HTMLElement>("#jobs-list")!;
const activityFilter = document.createElement("select");
activityFilter.className = "activity-filter";
activityFilter.setAttribute("aria-label", "Filter activity by Enclave");
jobsList.before(activityFilter);
const jobs = loadJobs();
function saveJobs(): void { persistJobs(jobs); }
function addJob(name: string, detail: string, enclave = current?.label, profileId = current?.profileId): Job { const job = { name, detail, enclave, profileId, state: "running" as const, at: new Date().toISOString() }; jobs.unshift(job); saveJobs(); renderJobs(); return job; }
function finishJob(job: Job, state: "succeeded" | "failed", detail: string): void { job.state = state; job.detail = detail; saveJobs(); renderJobs(); }
function renderJobs(): void {
  const selected = activityFilter.value;
  const enclaves = [...new Set(jobs.map((job) => job.enclave ?? "Other"))];
  activityFilter.replaceChildren(new Option("All Enclaves", ""), ...enclaves.map((enclave) => new Option(enclave, enclave)));
  activityFilter.value = enclaves.includes(selected) ? selected : "";
  const visible = selected ? jobs.filter((job) => (job.enclave ?? "Other") === selected) : jobs;
  jobsList.replaceChildren(...(visible.length ? visible.map((job) => {
    const row = document.createElement("div");
    row.className = `job ${job.state}`;
    const profile = profiles.find((item) => item.id === job.profileId) ?? profiles.find((item) => item.name === job.enclave);
    const actions: HTMLElement[] = [];
    if (profile) actions.push(actionButton("Open", () => void openEnclave(profile), "secondary"));
    if (job.state === "failed" && profile) actions.push(actionButton("Retry check", () => void checkEnclave(profile), "secondary"));
    row.append(el("span", { textContent: `${new Date(job.at).toLocaleString()} · ${job.enclave ?? "Other"} · ${job.name} · ${job.state} · ${job.detail}` }), ...actions);
    return row;
  }) : [Object.assign(document.createElement("p"), { className: "snapshot-shared", textContent: "No activity for this Enclave." })]));
}
activityFilter.addEventListener("change", renderJobs);
let worktreeReady = false;
let sourceBranches: string[] = [];
let profiles: ConnectionProfile[] = [];
let savedCredentials: Credential[] = [];
let current: Connection | undefined;
let latestProbe = 0;
let connected = false;
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
  if (command === "create_credential") {
    const credential = args.credential as Credential;
    if (demoStore.credentials.some((item) => item.id === credential.id)) throw new Error("credential already exists; create a new credential instead");
    demoStore.credentials.push(credential);
  }
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
  if (!demoMode) return invokeTauri<T>(command, _args);
  await new Promise((resolve) => window.setTimeout(resolve, 180));
  if (command === "current_user") return "developer" as T;
  if (command === "wsl_default_user") return "developer" as T;
  if (command === "test_connection") return "developer" as T;
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
    workspace_action: { plan: { ready: true, blockers: [], changes: ["update workspace", "run orcan sync"] } },
    runtime_action: null,
    ssh_host_key: { destination: "demo.example", algorithm: "ssh-ed25519", fingerprint: "SHA256:demo", status: "trusted" },
    trust_ssh_host_key: null,
    check_online_provision: { user: "developer", installedVersion: "orcan demo" },
    check_docker: { available: true, version: "27.5.1", detail: "Docker daemon is ready" },
    provision_online: { version: "orcan demo" },
  };
  return (responses[command] ?? {}) as T;
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
const needsManagedProjects = new Set(["sandbox", "repositories", "worktrees"]);

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
  renderEnclaveStatus();
}

function unlockStudio(report: ProbeReport): void {
  connected = true;
  activeGroup.hidden = false;
  for (const item of navigationItems.filter((item) => item.classList.contains("gated"))) {
    item.hidden = needsManagedProjects.has(item.dataset.viewTarget ?? "") && !report.capabilities.managed_projects;
  }
  healthPanel.hidden = false;
  const agents = Object.entries(report.runtime.docker.agents ?? {}).filter(([, available]) => available).map(([name]) => name);
  healthTitle.textContent = report.runtime.docker.container.state === "running" ? "Ready" : "Attention needed";
  overviewRuntime.textContent = report.runtime.docker.container.state;
  overviewConfig.textContent = contextSourceLabel(report);
  overviewAgents.textContent = agents.length ? agents.join(", ") : "Not reported";
  overviewAccess.textContent = accessExposure(report.runtime.launch);
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

function renderEnclaveConfiguration(report: ProbeReport): void {
  const fallback: Array<{ id: string; label: string; state: "editable" | "locked"; value: string; detail: string; action?: "contexts" | "runtime" }> = [
    { id: "context", label: "Workspace context", state: canEditContext(report) ? "editable" : "locked", value: contextSourceLabel(report), detail: canEditContext(report) ? "Workspaces and project membership are planned, confirmed, then reconciled." : contextEditMessage(), action: "contexts" as const },
    { id: "lifecycle", label: "Container lifecycle", state: "editable", value: report.runtime.docker.container.state, detail: "Start, stop, and restart are available. Restart reuses Orcan's recorded launch flags.", action: "runtime" as const },
    { id: "resources", label: "Container resources", state: "locked", value: report.runtime.resources ? `CPU ${report.runtime.resources.cpus ?? "—"} · RAM ${report.runtime.resources.memory ?? "—"}` : "Not reported", detail: "CPU and memory are supplied at container creation; Studio reports them but does not rewrite Docker start configuration." },
  ];
  const settings = report.control?.settings?.length ? report.control.settings : fallback;
  const option = (title: string, value: string, detail: string, state: "editable" | "locked", button?: HTMLButtonElement): HTMLElement =>
    el("div", { className: `enclave-config-option ${state}` }, el("div", {}, el("strong", { textContent: title }), el("span", { textContent: value }), el("small", { textContent: detail })), el("span", { className: "config-state", textContent: state === "editable" ? "Editable" : "Locked" }), ...(button ? [button] : []));
  enclaveConfigOptions.replaceChildren(...settings.map((setting) => {
    let button: HTMLButtonElement | undefined;
    if (setting.action === "contexts") {
      button = actionButton("Manage", () => showView("contexts"), "secondary");
    } else if (setting.action === "runtime") {
      button = actionButton("Controls", () => {
        showView("overview");
        document.querySelector<HTMLElement>(".runtime-controls")?.scrollIntoView({ behavior: "smooth", block: "center" });
      }, "secondary");
    }
    if (button && setting.state === "locked") {
      button.disabled = true;
      button.title = setting.detail;
    }
    return option(setting.label, setting.value, setting.detail, setting.state, button);
  }));
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
  void connect(current).catch(() => {
    if (current?.profileId) enclaveStatus.set(current.profileId, { state: "offline", at: Date.now() });
    renderStore();
  });
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
let restoredMapFor: string | undefined;
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
      const startY = sourceBox.top - bounds.top + sourceBox.height / 2;
      const endX = targetBox.left - bounds.left + targetBox.width / 2;
      const endY = targetBox.top - bounds.top + targetBox.height / 2;
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
    const project = raw ? parseDraggedProject(raw) : undefined;
    if (project) onDrop(project);
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
      saveMapState();
      renderEnclaveMap(report);
    });
    const list = el("div", { className: "workspace-parent-groups" });
    const rootProjects = el("ul", { className: "workspace-root-projects" });
    const projectGroups = new Map<string, HTMLUListElement>();
    for (const project of projects) {
      const ref = { name: projectName(project), path: project.path, kind: project.kind };
      const others = (project.repository_id ? sharedIn.get(project.repository_id) ?? [] : []).filter((name) => name !== workspace.name);
      const removing = drafts.some((draft) => draft.action === "detach" && draft.project.path === project.path);
      const alertTags = projectAlerts(report, project).filter((alert) => alert !== "uncommitted" && alert !== "missing");
      const tags = [project.branch && el("span", { className: "tag", textContent: project.branch }), project.dirty && el("span", { className: "tag warn", textContent: "uncommitted" }), project.kind === "missing" && el("span", { className: "tag danger", textContent: "missing" }), ...alertTags.map((alert) => el("span", { className: "tag warn", textContent: alert })), others.length > 0 && el("span", { className: "tag", textContent: `also in ${others.join(", ")}` }), removing && el("span", { className: "tag removing", textContent: "detach planned" })].filter((tag): tag is HTMLSpanElement => Boolean(tag));
      const remove = actionButton("✕", () => void reviewChange("detach", workspace.name, ref), "chip-remove");
      remove.title = `Remove ${ref.name} from ${workspace.name} (files stay)`;
      const parent = projectGroup(report, project.path);
      const projectList = parent
        ? projectGroups.get(parent) ?? projectGroups.set(parent, el("ul")).get(parent)!
        : rootProjects;
      projectList.append(el("li", {}, projectChip(ref, tags, workspace.name, removing ? "removing" : "current"), remove, el("small", { textContent: project.path })));
    }
    if (rootProjects.children.length) list.append(rootProjects);
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
    return { parent: projectGroup(report, project.path), item: el("span", { className: "tray-item" }, chip, action) };
    });
  const showCreate = !focusedWorkspace && activeMapFilters.size === 0;
  workspaceCards.replaceChildren(...(cards.length ? cards : [el("p", { className: "hint map-empty", textContent: "No workspace or planned relation matches this filter." })]), ...(showCreate ? [create] : []));
  const groups = chips.reduce<Map<string | undefined, HTMLElement[]>>((all, chip) => {
    (all.get(chip.parent) ?? all.set(chip.parent, []).get(chip.parent)!).push(chip.item);
    return all;
  }, new Map());
  const rootItems = groups.get(undefined) ?? [];
  const groupNodes = [...groups.entries()].filter(([parent]) => parent).sort(([left], [right]) => left!.localeCompare(right!)).map(([parent, items]) => el("details", { className: "project-parent", open: true }, el("summary", { title: parent }, el("span", { textContent: parentLabel(parent!) }), el("small", { textContent: `${items.length} project${items.length === 1 ? "" : "s"}` })), el("div", { className: "tray-chips" }, ...items)));
  sandboxTray.replaceChildren(el("div", { className: "tray-header" }, el("strong", { textContent: `Available projects and folders (${chips.length})` }), el("span", { className: "hint", textContent: `${report.paths.projects_root}` })), chips.length ? el("div", { className: "project-parent-groups" }, ...(rootItems.length ? [el("div", { className: "tray-chips root-projects" }, ...rootItems)] : []), ...groupNodes) : el("p", { className: "hint", textContent: query ? "No project or folder matches this filter." : "No projects or folders in the sandbox yet. Import a repository in Repositories." }));
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
    el("span", { textContent: `${workspace.projects.length} connections` }),
    el("span", { textContent: `${worktrees} worktrees` }),
    el("span", { textContent: `${mounts} mounts` }),
    el("span", { className: dirty || missing ? "warn" : "", textContent: dirty ? `${dirty} dirty` : missing ? `${missing} missing` : "ready" }),
  );
  workspaceInspectorAgent.textContent = `After applying the plan and running sync, the agent sees: ${names.length ? names.slice(0, 6).join(" · ") + (names.length > 6 ? ` · +${names.length - 6} more` : "") : "no projects or mounts yet"}.`;
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
      const source = parentCandidates(report, parentRuns).find((candidate) => candidate.repositoryId === project.repository_id && candidate.eligible);
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
const activeMapFilters = new Set<MapFilter>();
function restoreMapState(): void {
  const key = current ? enclaveChangeKey(current) : undefined;
  if (!key || restoredMapFor === key) return;
  restoredMapFor = key;
  const saved = loadMapState(key);
  activeMapFilters.clear();
  for (const filter of saved?.filters ?? []) activeMapFilters.add(filter);
  focusedWorkspace = saved?.workspace;
}
function saveMapState(): void {
  if (!current) return;
  persistMapState(enclaveChangeKey(current), { filters: [...activeMapFilters], workspace: focusedWorkspace });
}
for (const button of mapFilterChips.querySelectorAll<HTMLButtonElement>("[data-map-filter]")) {
  button.addEventListener("click", () => {
    const filter = button.dataset.mapFilter as MapFilter;
    activeMapFilters.has(filter) ? activeMapFilters.delete(filter) : activeMapFilters.add(filter);
    button.classList.toggle("active", activeMapFilters.has(filter));
    saveMapState();
    if (currentReport) renderEnclaveMap(currentReport);
  });
}
mapFocusClear.addEventListener("click", () => { focusedWorkspace = undefined; saveMapState(); if (currentReport) renderEnclaveMap(currentReport); });
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
let pendingChange: PendingChange | undefined;
let pendingPlan: { ready: boolean; changes: string[] } | undefined;

function saveQueuedChanges(): void {
  persistQueuedChanges(queuedChanges);
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
  const conflicts = draftConflicts(changes);
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
  if (draftConflicts(changes).size) {
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
  if (!changes.length || draftConflicts(changes).size) return;
  applyChanges.replaceChildren(...changes.map((change) => {
    const checkbox = el("input", { type: "checkbox", checked: true, value: change.id });
    return el("li", { className: "apply-choice" }, el("label", { className: "toggle" }, el("span", { textContent: changeTitle(change) }), checkbox));
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

let currentReport: ProbeReport | undefined;

function renderConnectionDoctor(report: ProbeReport): void {
  const target = current?.target.kind === "ssh" ? "SSH" : current?.target.kind === "wsl2" ? "WSL2" : "Local";
  const editable = canEditContext(report);
  const reconnect = actionButton("Reconnect", () => { if (current) void connect(current, settingsResult); }, "secondary");
  const profile = actionButton("Open profile", () => { showView("profiles"); const selected = profiles.find((item) => item.id === current?.profileId); if (selected) openProfileForm(selected); }, "secondary");
  connectionDoctor.replaceChildren(
    el("header", {}, el("div", {}, el("p", { className: "eyebrow", textContent: "CONNECTION DOCTOR" }), el("h3", { textContent: editable ? "Context is writable" : "Context is read-only" })), el("div", { className: "actions compact" }, reconnect, profile)),
    el("dl", {},
      el("div", {}, el("dt", { textContent: "Target" }), el("dd", { textContent: target })),
      el("div", {}, el("dt", { textContent: "User" }), el("dd", { textContent: report.host.user ?? "Not reported" })),
      el("div", {}, el("dt", { textContent: "Configuration" }), el("dd", { textContent: report.context.configuration.path ?? "Not reported" })),
      el("div", {}, el("dt", { textContent: "Workspace index" }), el("dd", { textContent: report.paths.workspace_metadata_root })),
    ),
    el("p", { className: "hint", textContent: editable ? "Orcan confirmed that this profile can plan and apply context changes." : contextEditMessage() }),
  );
}

function canEditContext(report = currentReport): boolean {
  const declared = report?.control?.operations?.context_edit;
  if (declared) return declared.available;
  const configuration = report?.context.configuration;
  return Boolean(configuration && (configuration.editable ?? (configuration.source === "config" || (!configuration.source && configuration.state === "present"))));
}

function contextSourceLabel(report: ProbeReport): string {
  const source = report.context.configuration.source ?? (report.context.configuration.state === "present" ? "config" : "runtime_index");
  return source === "config" ? "orcan.config.json" : source === "runtime_index" ? "synced workspace index · read-only" : "no Orcan context source";
}

function contextEditMessage(): string {
  return currentReport?.control?.operations?.context_edit?.reason
    ?? "This Enclave reports only its last synced workspace index. Reconnect where orcan.config.json is available before changing context.";
}

function setContextNotice(message: string): void {
  contextWorkspaceNotice.textContent = message;
  result.textContent = message;
}

function selectedWorkspaces(): string[] {
  return Array.from(worktreeWorkspaces.selectedOptions, (option) => option.value);
}

function renderWorktreeExisting(): void {
  const report = currentReport;
  const candidate = report && parentCandidates(report, parentRuns).find((item) => item.path === worktreeRepo.value);
  const selected = selectedWorkspaces();
  if (!report || !candidate || !selected.length) {
    worktreeExisting.textContent = "Choose a Git source and first workspace to inspect existing branches.";
    worktreeSourceState.textContent = "Choose a Git source to inspect its branch.";
    worktreeSourceUpdate.hidden = true;
    return;
  }
  const status = candidate.dirty ? "has uncommitted changes" : candidate.behind ? `${candidate.behind} commit${candidate.behind === 1 ? "" : "s"} behind ${candidate.upstream ?? "upstream"}` : "up to date";
  worktreeSourceState.textContent = `${candidate.branch ?? "detached HEAD"} · ${status}`;
  worktreeSourceUpdate.hidden = !candidate.branch;
  worktreeSourceUpdate.disabled = Boolean(candidate.dirty) || report.control?.operations?.parent_update?.available === false;
  worktreeSourceUpdate.title = candidate.dirty ? "Commit or stash changes before updating this parent." : "Preview and run git pull --ff-only before creating a worktree.";
  const branches = selected.flatMap((workspaceName) => {
    const workspace = report.context.workspaces.find((item) => item.name === workspaceName);
    return (workspace?.projects ?? [])
      .filter((project) => project.repository_id === candidate.repositoryId && project.path.startsWith(report.paths.managed_worktrees_root))
      .map((project) => `${workspaceName} · ${project.branch ?? project.name ?? "detached"}`);
  });
  const connected = branches.length
    ? `Already connected from this source: ${branches.join(" · ")}.`
    : "No managed branches from this source are connected to the first workspace.";
  const preview = sourceBranches.length
    ? ` Existing local branches (${sourceBranches.length}): ${sourceBranches.slice(0, 8).join(" · ")}${sourceBranches.length > 8 ? ` · +${sourceBranches.length - 8} more` : ""}.`
    : " No local branches reported yet.";
  worktreeExisting.textContent = `${connected}${preview}`;
}

function renderWorktreeBranchState(): void {
  const branch = worktreeBranch.value.trim();
  const exists = Boolean(branch) && sourceBranches.includes(branch);
  worktreeBranchState.textContent = !branch
    ? "Enter a branch name."
    : exists
      ? "Existing branch · this worktree will check it out."
      : "New branch · Orcan will create it for this worktree.";
  worktreeBranchState.classList.toggle("existing", exists);
}

function renderBranchBrowser(): void {
  const query = branchSearch.value.trim().toLowerCase();
  const visible = sourceBranches.filter((branch) => branch.toLowerCase().includes(query));
  branchSummary.textContent = `Local branches (${sourceBranches.length})`;
  branchBrowser.hidden = sourceBranches.length === 0;
  branchList.replaceChildren(...visible.slice(0, 40).map((branch) => actionButton(branch, () => { worktreeBranch.value = branch; worktreeReady = false; worktreeApply.disabled = true; renderWorktreeBranchState(); }, "secondary")));
}

async function refreshWorktreeBranches(): Promise<void> {
  if (!current || !worktreeRepo.value) {
    sourceBranches = [];
    renderWorktreeExisting();
    return;
  }
  worktreeExisting.textContent = "Reading local branches from the Git source…";
  try {
    const response = await invoke<{ branches: string[] }>("worktree_branches", {
      enclave: enclaveInput(current), repo: worktreeRepo.value,
      worktreesRoot: setting("setting-worktrees-root").textContent,
    });
    sourceBranches = response.branches;
  } catch {
    sourceBranches = [];
  }
  renderWorktreeExisting();
  renderWorktreeBranchState();
  renderBranchBrowser();
}

function renderWorktreeChoices(report: ProbeReport): void {
  const previousRepository = worktreeRepo.value;
  const previousWorkspaces = new Set(selectedWorkspaces());
  const sources = parentCandidates(report, parentRuns).filter((candidate) => candidate.eligible);
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
  void refreshWorktreeBranches();
}

function renderImportChoices(report: ProbeReport): void {
  const previous = importParent.value;
  const directories = report.context.managed_projects
    .filter((project) => project.kind === "directory")
    .map((project) => ({ path: project.path, name: project.path.split("/").filter(Boolean).at(-1) ?? project.path }));
  const choices = [{ path: report.paths.projects_root, name: "Sandbox root (default)" }, ...directories];
  importParent.replaceChildren(...choices.map((choice) => new Option(choice.name, choice.path)));
  importParent.value = choices.some((choice) => choice.path === previous) ? previous : report.paths.projects_root;
  const auth = report.control?.settings?.find((setting) => setting.id === "git_auth");
  importAuth.textContent = auth?.detail ?? "Git authentication is resolved by Orcan on this machine; Studio never receives SSH keys or their contents.";
  importDestination.textContent = `Orcan will clone into ${importParent.options[importParent.selectedIndex]?.text ?? "the selected folder"}/<repository name>.`;
}

function renderSnapshot(report: ProbeReport): void {
  report = normalizeProbeReport(report);
  currentReport = report;
  // The navigation is the essential connection result.  Map decorations and
  // inventories below are helpful, but must never keep a valid report locked.
  unlockStudio(report);
  restoreMapState();
  for (const button of mapFilterChips.querySelectorAll<HTMLButtonElement>("[data-map-filter]")) button.classList.toggle("active", activeMapFilters.has(button.dataset.mapFilter as MapFilter));
  renderEnclaveMap(report);
  snapshot.hidden = false;
  snapshotRoot.textContent = report.paths.projects_root;
  snapshotWorkspaces.textContent = String(report.context.workspaces.length);
  snapshotProjects.textContent = String(report.context.managed_projects.length);
  renderContextWorkspaceList(report);
  renderSandboxProjects(report);
  sandboxSettings.hidden = false;
  renderConnectionDoctor(report);
  setting("setting-home").textContent = report.paths.home;
  setting("setting-data").textContent = report.paths.data;
  setting("setting-projects-root").textContent = report.paths.projects_root;
  setting("setting-workspaces-root").textContent = report.paths.workspace_metadata_root;
  setting("setting-worktrees-root").textContent = report.paths.managed_worktrees_root;
  setting("setting-config-state").textContent = report.context.configuration.revision ? `${contextSourceLabel(report)} · ${report.context.configuration.revision}` : contextSourceLabel(report);
  settingsSync.disabled = !canEditContext(report);
  if (!canEditContext(report)) settingsResult.textContent = contextEditMessage();
  setting("setting-access").textContent = accessExposure(report.runtime.launch);
  renderEnclaveConfiguration(report);
  renderImportChoices(report);
  renderWorktreeChoices(report);
  const resources = report.runtime.resources;
  settingResources.textContent = resources ? `CPU ${resources.cpus ?? "—"} · RAM ${resources.memory ?? "—"} · SHM ${resources.shm_size ?? "—"}` : "Not reported";
  const agents = Object.entries(report.runtime.docker.agents ?? {}).filter(([, available]) => available).map(([name]) => name);
  settingAgents.textContent = agents.length ? agents.join(" · ") : "No image manifest reported";
  cleanupSuggestions.replaceChildren(el("p", { className: "hint", textContent: "Loading managed worktrees…" }));
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

function isPrimaryBranch(branch?: string): boolean {
  return branch === "main" || branch === "master";
}

function renderSandboxProjects(report: ProbeReport): void {
  sandboxPath.textContent = report.paths.projects_root;
  const parents = new Map(parentCandidates(report, parentRuns).map((parent) => [parent.path, parent]));
  const projects = new Map(report.context.managed_projects.map((project) => [project.path, project]));
  for (const parent of parents.values()) {
    if (!projects.has(parent.path)) projects.set(parent.path, { path: parent.path, kind: "git_repository" });
  }
  const rows = [...projects.values()]
    .sort((left, right) => left.path.localeCompare(right.path))
    .map((project) => {
      const parent = parents.get(project.path);
      const name = projectName(project);
      const branch = parent?.branch ?? project.branch;
      const dirty = parent?.dirty ?? project.dirty;
      const state = [
        branch,
        dirty ? "uncommitted changes" : undefined,
        parent?.upstream ?? project.upstream,
        parent?.behind || project.behind ? `${parent?.behind ?? project.behind} behind` : undefined,
        parent?.ahead || project.ahead ? `${parent?.ahead ?? project.ahead} ahead` : undefined,
        parent?.worktree_count ? `${parent.worktree_count} worktrees` : undefined,
        project.writable === false || parent?.readOnly ? "read-only" : undefined,
      ].filter(Boolean).join(" · ") || project.kind;
      const update = parent && isPrimaryBranch(parent.branch)
        ? actionButton("Update", () => void updateSandboxParent(parent), "secondary")
        : undefined;
      if (update && parent) {
        update.disabled = !parent.eligible || Boolean(parent.dirty) || currentReport?.control?.operations?.parent_update?.available === false;
        update.title = update.disabled
          ? parent.dirty ? "Parent has uncommitted changes; update is blocked" : "Orcan reports this parent cannot be updated"
          : `Preview and update ${parent.branch} with git pull --ff-only`;
      }
      const branchLabel = parent && !isPrimaryBranch(parent.branch) && branch
        ? ` · ${branch} is not a main/master parent`
        : "";
      return el("article", { className: "sandbox-project-row" }, projectKindIcon({ name, path: project.path, kind: project.kind }), el("div", { className: "sandbox-project-info" }, el("strong", { textContent: name }), el("small", { textContent: `${state}${branchLabel}` }), el("code", { textContent: project.path })), ...(update ? [update] : []));
    });
  sandboxProjects.replaceChildren(...(rows.length ? rows : [el("p", { className: "hint", textContent: "No projects or folders are reported under this Sandbox root." })]));
}

function renderContextWorkspaceList(report: ProbeReport): void {
  const editable = Boolean(report && canEditContext(report));
  const selected = focusedWorkspace && report.context.workspaces.some((workspace) => workspace.name === focusedWorkspace)
    ? focusedWorkspace : report.context.workspaces[0]?.name;
  focusedWorkspace = selected;
  contextWorkspaceList.replaceChildren(...report.context.workspaces.map((workspace) => {
    const dirty = workspace.projects.filter((project) => project.dirty).length;
    const button = el("button", { type: "button", className: "context-workspace-item" }, el("span", { className: "context-workspace-icon", textContent: "◫" }), el("span", {}, el("strong", { textContent: workspace.name }), el("small", { textContent: `${workspace.projects.length} · ${dirty ? `${dirty} dirty` : "clean"}` })));
    button.classList.toggle("active", workspace.name === selected);
    button.addEventListener("click", () => { focusedWorkspace = workspace.name; saveMapState(); renderContextWorkspaceList(report); });
    return button;
  }));
  const workspace = report.context.workspaces.find((item) => item.name === selected);
  if (!workspace) { contextWorkspaceDetail.replaceChildren(el("p", { className: "hint", textContent: "No workspace selected." })); return; }
  const add = actionButton("＋", () => { showView("overview"); renderEnclaveMap(report); sandboxTray.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, "secondary");
  add.title = "Add a project from the map";
  const worktree = actionButton("⑂", () => { showView("worktrees"); for (const option of worktreeWorkspaces.options) option.selected = option.value === workspace.name; renderWorktreeExisting(); }, "secondary");
  worktree.title = "Create a new Git worktree";
  const rename = actionButton("Rename", () => void manageWorkspace("rename", workspace.name), "secondary");
  rename.title = "Rename workspace";
  const remove = actionButton("×", () => void manageWorkspace("remove", workspace.name), "secondary");
  remove.title = "Remove empty workspace";
  if (!editable) {
    for (const button of [worktree, rename, remove]) {
      button.disabled = true;
      button.title = contextEditMessage();
    }
  }
  const projects = workspace.projects.map((project) => {
    const detach = actionButton("×", () => void reviewChange("detach", workspace.name, { name: projectName(project), path: project.path, kind: project.kind }), "context-project-detach");
    detach.title = editable ? `Detach ${projectName(project)} from ${workspace.name}` : contextEditMessage();
    detach.disabled = !editable;
    const parent = parentForProject(report, project, parentRuns);
    const parentState = parent
      ? parent.dirty
        ? `parent ${parent.branch ?? "branch"} dirty`
        : parent.behind
          ? `parent ${parent.branch ?? "branch"} · ${parent.behind} behind`
          : `parent ${parent.branch ?? "branch"} · up to date`
      : undefined;
    let update: HTMLButtonElement | undefined;
    if (parent) {
      update = actionButton("↻", () => void updateProjectParent(parent, workspace.name, projectName(project)), "context-project-update");
      update.title = parent.dirty ? "Parent has changes; update is blocked" : `Check and update ${parent.branch ?? "parent"}`;
      update.disabled = parent.dirty || !parent.branch || currentReport?.control?.operations?.parent_update?.available === false;
    }
    return el("div", { className: "context-project-row" }, projectKindIcon({ ...project, name: projectName(project) }), el("div", {}, el("strong", { textContent: projectName(project) }), el("small", { textContent: [project.branch, project.dirty && "dirty", parentState, project.writable === false && "read-only"].filter(Boolean).join(" · ") || project.kind })), ...(update ? [update] : []), detach);
  });
  const open = actionButton("⌁", () => { showView("overview"); renderEnclaveMap(report); enclaveMap.scrollIntoView({ behavior: "smooth", block: "start" }); });
  open.title = "Open relationship map";
  contextWorkspaceNotice.textContent = editable ? "" : `Read-only · ${contextSourceLabel(report)}. ${contextEditMessage()}`;
  contextWorkspaceDetail.replaceChildren(el("header", {}, el("div", {}, el("p", { className: "eyebrow", textContent: "WORKSPACE" }), el("h3", { textContent: workspace.name })), open), el("div", { className: "actions compact" }, add, worktree, rename, remove), contextWorkspaceNotice, el("div", { className: "context-project-list" }, ...(projects.length ? projects : [el("p", { className: "hint", textContent: "Empty workspace — add its first project." })])));
}

async function updateProjectParent(parent: ParentCandidate, workspace: string, project: string): Promise<void> {
  await updateParent(parent, `${project}'s parent ${parent.branch}`, (message) => setContextNotice(message), `for ${workspace}`);
}

async function updateSandboxParent(parent: ParentCandidate): Promise<void> {
  await updateParent(parent, `${parent.name} ${parent.branch}`, (message) => { sandboxResult.textContent = message; setContextNotice(message); });
}

async function updateParent(parent: ParentCandidate, label: string, reportStatus: (message: string) => void, completion = ""): Promise<void> {
  if (!current || !parent.branch || parent.dirty) return;
  reportStatus(`Checking ${label}…`);
  try {
    const response = await invoke<{ plan: { head: string; remote_head?: string; ready: boolean; blockers: string[] } }>("parent_plan", { enclave: enclaveInput(current), path: parent.path, branch: parent.branch });
    if (!response.plan.ready) {
      reportStatus(response.plan.blockers.join(" · "));
      return;
    }
    const remote = response.plan.remote_head?.slice(0, 8) ?? "origin";
    if (!window.confirm(`Update ${label}?\n${response.plan.head.slice(0, 8)} → ${remote}\n\nOrcan will run git pull --ff-only.`)) return;
    reportStatus(`Updating ${parent.branch}…`);
    await invoke("parent_apply", { enclave: enclaveInput(current), path: parent.path, branch: parent.branch, expectedHead: response.plan.head });
    rememberParentRun(parentRuns, parent.path, parent.branch);
    reportStatus(`Updated ${label}${completion ? ` ${completion}` : ""}.`);
    await connect(current);
  } catch (error) {
    reportStatus(`Parent update failed: ${String(error)}`);
  }
}

async function manageWorkspace(action: "rename" | "remove", workspace: string): Promise<void> {
  if (!current || !canEditContext()) { setContextNotice(contextEditMessage()); return; }
  const newName = action === "rename" ? window.prompt(`New name for ${workspace}:`, workspace)?.trim() : undefined;
  if (action === "rename" && (!newName || newName === workspace)) return;
  try {
    const plan = await invoke<{ plan: { changes: string[]; blockers: string[]; ready: boolean } }>("workspace_action", { enclave: enclaveInput(current), action, workspace, newName, apply: false });
    if (!plan.plan.ready) { setContextNotice(plan.plan.blockers.join(" · ")); return; }
    if (!window.confirm(`${plan.plan.changes.join("\n")}\n\nApply this Orcan plan?`)) return;
    await invoke("workspace_action", { enclave: enclaveInput(current), action, workspace, newName, apply: true });
    setContextNotice(`${action === "rename" ? "Workspace renamed" : "Workspace removed"}. Run Orcan sync to reconcile mounts.`);
    await connect(current);
  } catch (error) { setContextNotice(`Workspace change failed: ${String(error)}`); }
}

async function refreshWorktreeInventory(root: string): Promise<void> {
  if (!current) return;
  try {
    const response = await invoke<{ worktrees: Array<{ path: string; project: string; branch?: string; dirty: boolean }> }>("worktree_inventory", { enclave: enclaveInput(current), worktreesRoot: root });
    if (!response.worktrees.length) {
      cleanupSuggestions.replaceChildren(el("p", { className: "hint", textContent: "No managed worktrees to remove." }));
      return;
    }
    const rows = response.worktrees.map((worktree) => {
      const bindings = currentReport?.context.workspaces.flatMap((workspace) => workspace.projects.filter((project) => project.path === worktree.path).map(() => workspace.name)) ?? [];
      const label = `${worktree.project}${worktree.branch ? ` · ${worktree.branch}` : ""}${worktree.dirty ? " · uncommitted" : ""}`;
      const actions = bindings.length
        ? bindings.map((workspace) => actionButton(`Detach ${workspace}`, () => void reviewChange("detach", workspace, { name: worktree.project, path: worktree.path, kind: "git_worktree" }), "secondary"))
        : [actionButton("Delete", () => void deleteWorktree(worktree.path, label), "danger-link")];
      return el("div", { className: `cleanup-item ${bindings.length ? "bound" : "orphan"}` }, el("div", {}, el("strong", { textContent: label }), el("small", { textContent: bindings.length ? `Attached to ${bindings.join(", ")} · detach before deleting` : "Ready to delete · local branch is kept" }), el("small", { textContent: worktree.path })), ...actions);
    });
    cleanupSuggestions.replaceChildren(...rows);
  } catch { /* The current context map remains usable if inventory is unavailable. */ }
}

async function deleteWorktree(path: string, label: string): Promise<void> {
  if (!current || !canEditContext()) { cleanupResult.textContent = contextEditMessage(); return; }
  cleanupResult.textContent = `Checking removal of ${label}…`;
  try {
    const response = await invoke<{ plan: { ready: boolean; blockers: string[] } }>("worktree_cleanup", { enclave: enclaveInput(current), path, worktreesRoot: setting("setting-worktrees-root").textContent, removeBranch: false, apply: false });
    if (!response.plan.ready) { cleanupResult.textContent = response.plan.blockers.join(" · "); return; }
    if (!window.confirm(`Delete worktree ${label}?\n\nThis removes only this checkout:\n${path}\n\nIts local Git branch is kept in the source repository.`)) return;
    const connection = current;
    const job = addJob("Worktree cleanup", label);
    await invoke("worktree_cleanup", { enclave: enclaveInput(connection), path, worktreesRoot: setting("setting-worktrees-root").textContent, removeBranch: false, apply: true });
    finishJob(job, "succeeded", path);
    cleanupResult.textContent = `Deleted ${label}.`;
    await connect(connection);
  } catch (error) { cleanupResult.textContent = `Removal failed: ${String(error)}`; }
}

const CHOOSE_SSH = "";
const SYSTEM_SSH = "__system__";
const INLINE_SSH = "__inline__";
let editingProfile: ConnectionProfile | undefined;
let credentialKind: "password" | "private_key" = "private_key";

/** randomUUID needs a secure context; the Tailscale UX preview is plain HTTP. */
function newId(): string {
  return crypto.randomUUID?.() ?? Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function showPane(name: string): void {
  const pane = document.querySelector<HTMLElement>(`[data-pane="${name}"]`);
  if (!pane) return;
  for (const sibling of pane.parentElement!.querySelectorAll<HTMLElement>(":scope > [data-pane]")) sibling.hidden = sibling !== pane;
  pane.querySelector<HTMLElement>("input:not([type=radio]):not([hidden])")?.focus();
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
  const user = profile.ssh?.username || credential?.username;
  const signIn = credential ? credential.name : profile.ssh?.authentication.kind && profile.ssh.authentication.kind !== "agent" ? "saved in profile" : "system SSH";
  return `SSH · ${user ? `${user}@` : ""}${profile.target.destination} · ${signIn}`;
}

// Credentials & keys

function refreshCredentialForm(): void {
  keyPathField.hidden = credentialKind !== "private_key";
  secretLabel.textContent = credentialKind === "private_key" ? "Key passphrase" : "Password";
  secretHint.textContent = credentialKind === "private_key"
    ? "Leave empty only when this key has no passphrase. A supplied passphrase is stored in the operating-system vault."
    : "Stored in the operating-system vault, never in Studio files.";
}

function openCredentialForm(kind: "password" | "private_key"): void {
  credentialKind = kind;
  showView("credentials");
  credentialFormTitle.textContent = kind === "password" ? "New password credential" : "New key credential";
  credentialName.value = "";
  credentialUser.value = "";
  keyPath.value = "";
  secret.value = "";
  credentialResult.textContent = "";
  refreshCredentialForm();
  showPane("credential-form");
}

function leaveCredentialForm(): void {
  secret.value = "";
  showPane("credentials");
}

async function saveCredential(): Promise<void> {
  const name = credentialName.value.trim();
  const username = credentialUser.value.trim();
  if (!name) { credentialResult.textContent = "Give the credential a name you will recognise, e.g. “Work laptop key”."; return; }
  if (!username || /\s/.test(username)) { credentialResult.textContent = "Enter the remote user without spaces, e.g. “developer”."; credentialUser.focus(); return; }
  let authentication: SshAuthentication;
  if (credentialKind === "private_key") {
    const path = keyPath.value.trim();
    if (!path) { credentialResult.textContent = "Enter the path to the private key file."; return; }
    authentication = { kind: "private_key", path, has_passphrase: secret.value.length > 0 };
  } else {
    if (!secret.value) { credentialResult.textContent = "Enter the password."; return; }
    authentication = { kind: "password" };
  }
  const credential: Credential = { id: newId(), name, username, authentication };
  credentialSave.disabled = true;
  try {
    await invoke("create_credential", { credential, secret: secret.value || null });
    await loadStore();
    result.textContent = `Credential “${name}” created. It cannot be edited; create a replacement when it changes.`;
    leaveCredentialForm();
  } catch (error) { credentialResult.textContent = `Could not save: ${String(error)}`; }
  finally { credentialSave.disabled = false; }
}

function renderCredentials(): void {
  credentialList.replaceChildren(...(savedCredentials.length ? savedCredentials.map((credential) => {
    const users = profileUsers(credential.id);
    const remove = actionButton("Delete", () => void deleteCredential(credential), "danger-link");
    remove.disabled = users.length > 0;
    remove.title = users.length ? `Used by ${users.join(", ")}` : "Delete this unused credential";
    return listItem(credential.name, `${credential.username} · ${authLabel(credential.authentication)} · permanent${users.length ? ` · used by ${users.join(", ")}` : ""}`, remove);
  }) : [emptyState("No credentials yet. Create a password or key credential when Studio itself must sign in to a remote server.", "New password credential", () => openCredentialForm("password"))]));
}

async function deleteCredential(credential: Credential): Promise<void> {
  if (!window.confirm(`Delete credential ${credential.name}? Its vault secret is removed too.`)) return;
  try {
    await invoke("delete_credential", { id: credential.id });
    await loadStore();
  } catch (error) { result.textContent = `Could not delete credential: ${String(error)}`; }
}

// Profiles

function renderCredentialOptions(selected?: string): void {
  const options = [new Option("Choose sign-in method…", CHOOSE_SSH), new Option("System SSH — SSH agent or ~/.ssh/config", SYSTEM_SSH), ...savedCredentials.map((item) => new Option(`${item.name} · ${item.username} · ${authLabel(item.authentication)}`, item.id))];
  const inline = editingProfile?.target.kind === "ssh" && !editingProfile.credential_id && editingProfile.ssh && editingProfile.ssh.authentication.kind !== "agent";
  if (inline) options.push(new Option("Legacy profile credential — replace it", INLINE_SSH));
  credentialSelect.replaceChildren(...options);
  credentialSelect.value = options.some((option) => option.value === selected) ? selected ?? CHOOSE_SSH : CHOOSE_SSH;
  refreshProfileForm();
}

function refreshProfileForm(): void {
  const location = radioValue("location");
  wslFields.hidden = location !== "wsl2";
  if (location === "wsl2") void discoverWslDistributions();
  sshFields.hidden = location !== "ssh";
  const value = credentialSelect.value;
  const system = value === SYSTEM_SSH;
  sshSystemUserField.hidden = !system;
  sshUser.disabled = !system;
  credentialHint.textContent = value === SYSTEM_SSH
    ? "Uses the same SSH setup as a terminal on this computer: its SSH agent and SSH configuration. Enter a user above only when your SSH configuration does not already choose one."
    : value === INLINE_SSH ? "Kept as saved. Choose a shared credential to reuse it across profiles."
    : value ? `Studio signs in natively as ${savedCredentials.find((item) => item.id === value)?.username ?? "the credential user"}. This user is fixed by the credential.` : "Choose system SSH or one immutable credential.";
  profileTestResult.textContent = "";
  profileTestHint.replaceChildren();
  profileTestHint.hidden = true;
}

let knownWslDistributions: string[] | undefined;
let wslUserRequest = 0;

async function showWslDefaultUser(): Promise<void> {
  const distribution = wslDistribution.value;
  if (!distribution) return;
  const request = ++wslUserRequest;
  try {
    const user = await invoke<string>("wsl_default_user", { distribution });
    if (request === wslUserRequest) wslDistributionHint.textContent = `Detected by Studio. WSL2 will use its default Linux user: ${user}. No password is needed for this local connection.`;
  } catch (error) {
    if (request === wslUserRequest) wslDistributionHint.textContent = `WSL distribution selected. Studio could not read its default Linux user: ${String(error)}`;
  }
}

async function discoverWslDistributions(): Promise<void> {
  if (knownWslDistributions) return;
  wslDistribution.disabled = true;
  try {
    const response = await invoke<unknown>("list_wsl_distributions");
    if (!Array.isArray(response) || !response.every((item) => typeof item === "string")) {
      throw new Error("WSL discovery is available only in the Windows Studio application.");
    }
    const distributions = response;
    knownWslDistributions = distributions;
    const selected = wslDistribution.value;
    wslDistribution.replaceChildren(
      new Option(distributions.length ? "Choose a WSL2 distribution…" : "No WSL2 distributions found", ""),
      ...distributions.map((distribution) => new Option(distribution, distribution)),
    );
    wslDistribution.value = distributions.includes(selected) ? selected : distributions.includes("Ubuntu") ? "Ubuntu" : distributions[0] ?? "";
    wslDistribution.disabled = distributions.length === 0;
    wslDistributionHint.textContent = distributions.length
      ? "Detected on this Windows computer. Choose the Linux distribution Studio should connect to."
      : "No WSL2 distributions were found. Install one with `wsl --install`, then reopen this profile.";
    if (distributions.length) void showWslDefaultUser();
  } catch (error) {
    wslDistribution.replaceChildren(new Option("WSL2 discovery unavailable", ""));
    wslDistributionHint.textContent = String(error).includes("available only")
      ? String(error)
      : `Studio could not query WSL: ${String(error)}`;
  }
}

function openProfileForm(profile?: ConnectionProfile): void {
  editingProfile = profile;
  showView("profiles");
  profileFormTitle.textContent = profile ? `Edit ${profile.name}` : "New profile";
  profileName.value = profile?.name ?? "";
  setRadio("location", profile?.target.kind ?? "ssh");
  wslDistribution.value = profile?.target.kind === "wsl2" ? profile.target.distribution : "";
  let host = profile?.target.kind === "ssh" ? profile.target.destination : "";
  let user = profile?.credential_id ? "" : profile?.ssh?.username ?? "";
  if (profile?.target.kind === "ssh" && !profile.credential_id && host.includes("@")) {
    user = host.slice(0, host.lastIndexOf("@"));
    host = host.slice(host.lastIndexOf("@") + 1);
  }
  sshHost.value = host;
  sshUser.value = user;
  sshUser.placeholder = "Optional; otherwise SSH config decides";
  profileDelete.hidden = !profile;
  renderCredentialOptions(profile?.credential_id ?? (profile?.ssh && profile.ssh.authentication.kind !== "agent" ? INLINE_SSH : profile ? SYSTEM_SSH : undefined));
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
  if (choice === CHOOSE_SSH) throw new Error("Choose system SSH or a credential for this remote server.");
  const selectedCredential = savedCredentials.find((credential) => credential.id === choice);
  const labelUser = choice === SYSTEM_SSH ? user : selectedCredential?.username;
  const label = name || `${labelUser ? `${labelUser}@` : ""}${host}`;
  if (choice === SYSTEM_SSH) {
    const target: Target = { kind: "ssh", destination: user ? `${user}@${host}` : host };
    return { profile: { id, name, target }, connection: { target, label } };
  }
  const target: Target = { kind: "ssh", destination: host };
  if (choice === INLINE_SSH && editingProfile) {
    return { profile: { id, name, target, ssh: { ...editingProfile.ssh!, username: user || undefined } }, connection: { target, label, profileId: editingProfile.id } };
  }
  return {
    profile: { id, name, target, credential_id: choice },
    connection: { target, label, credentialId: choice },
  };
}

async function testProfile(): Promise<void> {
  profileTestHint.replaceChildren();
  profileTestHint.hidden = true;
  let connection: Connection;
  try { connection = profileFromForm().connection; }
  catch (error) { profileTestResult.textContent = error instanceof Error ? error.message : String(error); return; }
  profileTest.disabled = true;
  profileTestResult.textContent = `Testing connection to ${connection.label}…`;
  try {
    if (!(await confirmSshHostKey(connection))) return;
    const user = await invoke<string>("test_connection", { enclave: enclaveInput(connection) });
    profileTestResult.textContent = `✓ Connected to ${connection.label}${user ? ` as ${user}` : ""}.`;
    profileTestHint.textContent = "Connection only succeeded. Studio did not check Orcan, Docker, projects, or settings.";
    profileTestHint.hidden = false;
  } catch (error) {
    showConnectionFailure(String(error));
  } finally { profileTest.disabled = false; }
}

async function confirmSshHostKey(connection: Connection): Promise<boolean> {
  if (connection.target.kind !== "ssh") return true;
  const offer = await invoke<SshHostKeyOffer>("ssh_host_key", { destination: connection.target.destination });
  if (offer.status === "trusted") return true;
  if (offer.status === "changed") {
    profileTestResult.textContent = "Studio could not verify this server’s identity.";
    profileTestHint.replaceChildren(
      el("strong", { textContent: "The server identity changed." }),
      el("span", { textContent: "For safety, Studio blocked the connection. Ask the server owner to confirm the new fingerprint, then remove the old saved server identity from this computer before trying again." }),
      technicalDetail(`SSH host key changed for ${offer.destination}.`),
    );
    profileTestHint.hidden = false;
    return false;
  }
  const message = `First connection to this server\n\n${offer.destination}\n${offer.algorithm}\n${offer.fingerprint}\n\nCompare this fingerprint with the server owner if you can. If it is the intended server, approve to save its public identity on this computer and continue.`;
  if (!window.confirm(message)) {
    profileTestResult.textContent = "SSH host key was not trusted; no connection was made.";
    return false;
  }
  await invoke("trust_ssh_host_key", { destination: connection.target.destination, fingerprint: offer.fingerprint });
  profileTestResult.textContent = `Server identity saved; testing connection to ${offer.destination}…`;
  return true;
}

function technicalDetail(detail: string): HTMLDetailsElement {
  return el("details", {}, el("summary", { textContent: "Technical detail" }), el("code", { textContent: detail }));
}

function showConnectionFailure(detail: string): void {
  const normalized = detail.toLowerCase();
  let title = "Studio could not connect.";
  let explanation = "Check the connection details, then try again.";
  if (/authentication|permission denied|rejected|publickey/.test(normalized)) {
    title = "The computer rejected the sign-in.";
    explanation = "Check that the selected credential has the right user and password or key. Credentials cannot be edited; create a replacement if a value changed.";
  } else if (/no (password|key-passphrase) is stored|vault|keyring/.test(normalized)) {
    title = "The saved sign-in secret is unavailable.";
    explanation = "This computer’s secure credential store no longer has the password or key passphrase. Create a replacement credential and select it for this profile.";
  } else if (/host.?key|known_hosts|host key verification/.test(normalized)) {
    title = "Studio could not verify the server’s identity.";
    explanation = "Do not continue until the server owner confirms its fingerprint. Studio never replaces a saved server identity automatically.";
  } else if (/wsl|distribution/.test(normalized)) {
    title = "The selected WSL2 Linux installation is unavailable.";
    explanation = "Choose a listed WSL2 distribution, or install and start WSL2 on this Windows computer before trying again.";
  } else if (/timed out|connection refused|resolve|unreachable|no route|not found/.test(normalized)) {
    title = "Studio could not reach the computer.";
    explanation = "Check the server address and port. If you use a private network, connect its VPN or Tailscale network first. The remote computer must be on and accept SSH connections.";
  }
  profileTestResult.textContent = `✕ ${title}`;
  profileTestHint.replaceChildren(el("strong", { textContent: explanation }), technicalDetail(detail));
  profileTestHint.hidden = false;
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
    result.textContent = `Profile “${built.profile.name}” saved. Use Provisioning or Enclaves when you are ready to work with Orcan.`;
    showPane("profiles");
    showView("profiles");
  } catch (error) { profileTestResult.textContent = `Could not save: ${String(error)}`; }
  finally { profileSave.disabled = false; }
}

function renderProfiles(): void {
  profileList.replaceChildren(...(profiles.length ? profiles.map((profile) => {
    return listItem(profile.name, describeProfile(profile), actionButton("Test connection", () => openProfileForm(profile), "secondary"), actionButton("Edit", () => openProfileForm(profile)));
  })
    : [emptyState("No profiles yet. Create one to save how Studio reaches a local, WSL2, or SSH computer.", "Create a profile", () => openProfileForm())]));
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
    persistCachedReport(cacheKey(profile.target), report);
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
  return loadCachedReport(cacheKey(profile.target));
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

async function openEnclaveSettings(profile: ConnectionProfile): Promise<void> {
  const connection = profileConnection(profile);
  const report = enclaveStatus.get(profile.id)?.report ?? cachedEnclaveReport(profile);
  if (report) {
    activate(connection, report);
    showView("settings");
    void checkEnclave(profile);
    return;
  }
  result.textContent = `Connecting to ${profile.name}…`;
  const status = await checkEnclave(profile);
  if (status.report) {
    activate(connection, status.report);
    showView("settings");
  }
}

type ImageInventory = { image: string; id: string; size: string };
let inspectedImage: ImageInventory | undefined;

function selectedProfile(select: HTMLSelectElement): ConnectionProfile | undefined {
  return profiles.find((profile) => profile.id === select.value);
}

type CliProvisionResult = { version: string; image?: string };
type CliProvisionCheck = { source: string; destination: string; image?: string };
type OnlineProvisionCheck = { user: string; installedVersion?: string };
let cliProvisionReady = false;
let onlineProvisionReadyProfileId: string | undefined;

function openProvisioning(profile?: ConnectionProfile): void {
  showView("provisioning");
  if (profile) onlineProvisionTarget.value = profile.id;
  renderOnlineProvision();
}

function renderOnlineProvision(): void {
  const selected = onlineProvisionTarget.value;
  onlineProvisionTarget.replaceChildren(
    new Option(profiles.length ? "Choose destination profile…" : "No saved profiles", ""),
    ...profiles.map((profile) => new Option(`${profile.name} · ${describeProfile(profile)}`, profile.id)),
  );
  onlineProvisionTarget.value = profiles.some((profile) => profile.id === selected) ? selected : "";
  const profile = selectedProfile(onlineProvisionTarget);
  onlineProvisionCheck.disabled = !profile;
  onlineProvisionRun.disabled = !profile || onlineProvisionReadyProfileId !== profile.id;
  if (!profiles.length) onlineProvisionResult.textContent = "Save a local, WSL2, or SSH profile first. A profile does not need Orcan installed yet.";
}

async function checkOnlineProvision(): Promise<void> {
  const profile = selectedProfile(onlineProvisionTarget);
  if (!profile) { onlineProvisionResult.textContent = "Choose a destination profile."; return; }
  onlineProvisionReadyProfileId = undefined;
  onlineProvisionCheck.disabled = true;
  onlineProvisionRun.disabled = true;
  onlineProvisionResult.textContent = `Checking ${profile.name} for online installation…`;
  try {
    const check = await invoke<OnlineProvisionCheck>("check_online_provision", { enclave: enclaveInput(profileConnection(profile)) });
    onlineProvisionReadyProfileId = profile.id;
    onlineProvisionRun.disabled = false;
    onlineProvisionResult.textContent = `Ready as ${check.user}. Bash, curl, Git, and Python 3 are available.${check.installedVersion ? ` Existing Orcan: ${check.installedVersion}.` : " Orcan is not installed yet."}`;
  } catch (error) {
    onlineProvisionResult.textContent = `Requirements check failed: ${String(error)}`;
  } finally {
    onlineProvisionCheck.disabled = false;
  }
}

async function provisionOnline(): Promise<void> {
  const profile = selectedProfile(onlineProvisionTarget);
  if (!profile) { onlineProvisionResult.textContent = "Choose a destination profile."; return; }
  if (onlineProvisionReadyProfileId !== profile.id) { onlineProvisionResult.textContent = "Check requirements before installing or updating Orcan."; return; }
  if (!window.confirm(`Install or update Orcan on ${profile.name}? Studio will run the official online installer on that destination. Existing Orcan source files may be updated; no Studio profile, project, configuration, or credential is transferred.`)) return;
  const job = addJob("Install or update Orcan", profile.name, profile.name, profile.id);
  onlineProvisionRun.disabled = true;
  onlineProvisionResult.textContent = `Installing or updating Orcan on ${profile.name}…`;
  try {
    const installed = await invoke<CliProvisionResult>("provision_online", { enclave: enclaveInput(profileConnection(profile)) });
    enclaveStatus.delete(profile.id);
    onlineProvisionResult.textContent = `Orcan ${installed.version} is ready on ${profile.name}. You can now create or connect an Enclave.`;
    finishJob(job, "succeeded", `Ready: ${installed.version}`);
    await checkEnclave(profile);
  } catch (error) {
    onlineProvisionResult.textContent = `Installation failed: ${String(error)}`;
    finishJob(job, "failed", String(error));
  } finally {
    onlineProvisionReadyProfileId = undefined;
    onlineProvisionRun.disabled = true;
  }
}

function renderCliProvision(): void {
  const source = selectedProfile(cliProvisionSource)?.id;
  const target = selectedProfile(cliProvisionTarget)?.id;
  const wslProfiles = profiles.filter((profile) => profile.target.kind === "wsl2");
  const sshProfiles = profiles.filter((profile) => profile.target.kind === "ssh");
  const option = (profile: ConnectionProfile) => new Option(`${profile.name} · ${describeTarget(profile.target)}`, profile.id);
  cliProvisionSource.replaceChildren(new Option(wslProfiles.length ? "Choose source profile…" : "No WSL2 source profiles", ""), ...wslProfiles.map(option));
  cliProvisionTarget.replaceChildren(new Option(sshProfiles.length ? "Choose destination profile…" : "No system-SSH destination profiles", ""), ...sshProfiles.map(option));
  cliProvisionSource.value = wslProfiles.some((profile) => profile.id === source) ? source! : wslProfiles[0]?.id ?? "";
  cliProvisionTarget.value = sshProfiles.some((profile) => profile.id === target) ? target! : sshProfiles[0]?.id ?? "";
  cliProvisionImageField.hidden = !cliProvisionImage.checked;
  cliProvisionCheck.disabled = !wslProfiles.length || !sshProfiles.length;
  cliProvisionRun.disabled = true;
  cliProvisionReady = false;
  if (cliProvisionCheck.disabled) cliProvisionResult.textContent = "Create a WSL2 source profile and a remote destination profile using System SSH. The remote needs a shell, tar, and Docker only when including an image.";
}

function cliProvisionInput(): { distribution: string; destination: string; destinationProfileId: string; destinationCredentialId?: string; destinationUsername?: string; image?: string } | undefined {
  const source = selectedProfile(cliProvisionSource);
  const target = selectedProfile(cliProvisionTarget);
  if (!source || source.target.kind !== "wsl2" || !target || target.target.kind !== "ssh") return undefined;
  const image = cliProvisionImage.checked ? cliProvisionImageName.value.trim() : undefined;
  if (cliProvisionImage.checked && !image) throw new Error("Choose a Docker image to include.");
  return {
    distribution: source.target.distribution,
    destination: target.target.destination,
    destinationProfileId: target.id,
    destinationCredentialId: target.credential_id,
    destinationUsername: target.ssh?.username,
    image,
  };
}

async function checkCliProvision(): Promise<void> {
  try {
    const input = cliProvisionInput();
    if (!input) return;
    cliProvisionReady = false;
    cliProvisionRun.disabled = true;
    cliProvisionCheck.disabled = true;
    cliProvisionResult.textContent = "Checking WSL, SSH, and remote requirements…";
    const checked = await invoke<CliProvisionCheck>("check_wsl_cli_provision", { input });
    cliProvisionReady = true;
    cliProvisionRun.disabled = false;
    cliProvisionResult.textContent = `Ready: WSL Orcan and tar are available; ${checked.destination} accepts SSH and has tar${checked.image ? " and Docker" : ""}.`;
  } catch (error) {
    cliProvisionResult.textContent = `Requirements check failed: ${String(error)}`;
  } finally {
    cliProvisionCheck.disabled = false;
  }
}

async function provisionCli(): Promise<void> {
  const source = selectedProfile(cliProvisionSource);
  const target = selectedProfile(cliProvisionTarget);
  if (!source || source.target.kind !== "wsl2" || !target || target.target.kind !== "ssh") return;
  if (!cliProvisionReady) return;
  let input: { distribution: string; destination: string; destinationProfileId: string; destinationCredentialId?: string; destinationUsername?: string; image?: string };
  try { input = cliProvisionInput()!; } catch (error) { cliProvisionResult.textContent = String(error); return; }
  const { image } = input;
  const contents = image ? `the Orcan CLI and ${image}` : "the Orcan CLI";
  if (!window.confirm(`Install ${contents} from ${source.name} on ${target.name}? The remote installation replaces only its Orcan CLI files; no profile, project, sandbox, or credential is transferred.`)) return;
  const job = addJob("Offline CLI provisioning", `${source.name} → ${target.name}${image ? ` · ${image}` : ""}`, target.name, target.id);
  cliProvisionRun.disabled = true;
  cliProvisionResult.textContent = "Building the clean kit in WSL and streaming it through SSH…";
  try {
    const installed = await invoke<CliProvisionResult>("provision_wsl_cli", { input });
    cliProvisionResult.textContent = `Installed ${installed.version} on ${target.name}${installed.image ? ` and imported ${installed.image}` : ""}. Use New Enclave to configure and start it.`;
    finishJob(job, "succeeded", `Installed ${installed.version}${installed.image ? ` · ${installed.image}` : ""}`);
  } catch (error) {
    cliProvisionResult.textContent = `Offline installation failed: ${String(error)}`;
    finishJob(job, "failed", String(error));
  } finally {
    cliProvisionRun.disabled = false;
  }
}

function renderImageTransfer(): void {
  const source = selectedProfile(imageTransferSource)?.id;
  const target = selectedProfile(imageTransferTarget)?.id;
  const wslProfiles = profiles.filter((profile) => profile.target.kind === "wsl2");
  const sshProfiles = profiles.filter((profile) => profile.target.kind === "ssh" && !profile.credential_id);
  imageTransferSource.replaceChildren(new Option(wslProfiles.length ? "Choose source profile…" : "No WSL2 source profiles", ""), ...wslProfiles.map((profile) => new Option(`${profile.name} · ${describeTarget(profile.target)}`, profile.id)));
  imageTransferTarget.replaceChildren(new Option(sshProfiles.length ? "Choose destination profile…" : "No system-SSH destination profiles", ""), ...sshProfiles.map((profile) => new Option(`${profile.name} · ${describeTarget(profile.target)}`, profile.id)));
  imageTransferSource.value = wslProfiles.some((profile) => profile.id === source) ? source! : wslProfiles[0]?.id ?? "";
  imageTransferTarget.value = sshProfiles.some((profile) => profile.id === target) ? target! : sshProfiles[0]?.id ?? "";
  const ready = Boolean(wslProfiles.length && sshProfiles.length);
  imageTransferInspect.disabled = !ready;
  imageTransferRun.disabled = true;
  if (!ready) imageTransferResult.textContent = "Create a WSL2 source profile and a remote destination profile using System SSH before transferring an image.";
}

/** One profile owns one current Enclave until Orcan gains multi-runtime support. */
function profileHasEnclave(profile: ConnectionProfile): boolean {
  const report = enclaveStatus.get(profile.id)?.report ?? cachedEnclaveReport(profile);
  return report?.context.configuration.source === "config" || report?.context.configuration.state === "present";
}

function profileCanCreateEnclave(profile: ConnectionProfile): boolean {
  const status = enclaveStatus.get(profile.id);
  return status?.state === "online"
    && !profileHasEnclave(profile)
    && Boolean(status.report?.capabilities.docker);
}

function renderEnclaveCreator(): void {
  const previous = enclaveCreateProfile.value;
  const available = profiles.filter(profileCanCreateEnclave);
  enclaveCreateProfile.replaceChildren(
    new Option(available.length ? "Choose available profile…" : "No available profiles", ""),
    ...available.map((profile) => new Option(profile.name, profile.id)),
  );
  enclaveCreateProfile.value = available.some((profile) => profile.id === previous) ? previous : "";
  enclaveCreatePlan.disabled = available.length === 0;
  enclaveCreateApply.disabled = true;
  if (!available.length) {
    const used = profiles.filter(profileHasEnclave).length;
    enclaveCreateResult.textContent = used
      ? "Every checked profile already owns an Enclave. One profile can create one Enclave."
      : "Check Orcan and Docker on a provisioned profile before creating its Enclave.";
  }
}

function enclaveTtydCredential(): string | undefined {
  if (!enclaveCreateTtydAuth.checked) return undefined;
  const user = enclaveCreateTtydUser.value.trim();
  const password = enclaveCreateTtydPassword.value;
  if (!user || !password || user.includes(":")) {
    throw new Error("Browser-terminal auth needs a user without ':' and a password.");
  }
  return `${user}:${password}`;
}

async function planEmptyEnclave(apply = false): Promise<void> {
  const profile = selectedProfile(enclaveCreateProfile);
  if (!profile) return;
  if (!profileCanCreateEnclave(profile)) {
    enclaveCreateResult.textContent = "This profile is not available for a new Enclave. Check Orcan first, or use its existing Enclave.";
    return;
  }
  enclaveCreateResult.textContent = apply ? "Creating empty Enclave…" : "Reading creation plan…";
  try {
    if (!apply) {
      const report = await invoke<ProbeReport>("probe", { enclave: enclaveInput(profileConnection(profile)) });
      if (!report.capabilities.docker) throw new Error("Docker is not available on this destination profile.");
    }
    await invoke("enclave_action", {
      enclave: enclaveInput(profileConnection(profile)),
      apply,
      withGit: enclaveCreateGit.checked,
      withDocker: enclaveCreateDocker.checked,
      withTtyd: enclaveCreateTtyd.checked,
      ttydCredential: enclaveTtydCredential(),
    });
    enclaveCreateResult.textContent = apply ? "Enclave created. Checking it now…" : "Plan ready: create empty config, sync it, then start the selected runtime access.";
    enclaveCreateApply.disabled = apply;
    if (apply) {
      enclaveCreateTtydPassword.value = "";
      await openEnclave(profile);
    }
  } catch (error) { enclaveCreateResult.textContent = `Enclave setup failed: ${String(error)}`; }
}

async function inspectTransferImage(): Promise<void> {
  const source = selectedProfile(imageTransferSource);
  if (!source || source.target.kind !== "wsl2") return;
  inspectedImage = undefined;
  imageTransferRun.disabled = true;
  imageTransferInspect.disabled = true;
  imageTransferResult.textContent = `Checking ${imageTransferName.value.trim()} in ${source.name}…`;
  try {
    const inventory = await invoke<ImageInventory>("wsl_image_inventory_command", { input: { distribution: source.target.distribution, image: imageTransferName.value.trim() } });
    inspectedImage = inventory;
    imageTransferResult.textContent = `Ready: ${inventory.image} · ${inventory.id} · ${inventory.size} bytes. Transfer streams this image directly to the selected remote Docker daemon.`;
    imageTransferRun.disabled = !selectedProfile(imageTransferTarget);
  } catch (error) { imageTransferResult.textContent = `Image check failed: ${String(error)}`; }
  finally { imageTransferInspect.disabled = false; }
}

async function transferImage(): Promise<void> {
  const source = selectedProfile(imageTransferSource);
  const target = selectedProfile(imageTransferTarget);
  if (!source || source.target.kind !== "wsl2" || !target || target.target.kind !== "ssh" || !inspectedImage) return;
  if (!window.confirm(`Transfer ${inspectedImage.image} (${inspectedImage.id}) from ${source.name} to ${target.name}? The remote Docker daemon will import the image.`)) return;
  const job = addJob("Image transfer", `${inspectedImage.image}: ${source.name} → ${target.name}`, target.name, target.id);
  imageTransferRun.disabled = true;
  imageTransferResult.textContent = `Transferring ${inspectedImage.image}; keep Studio open until Docker import completes…`;
  try {
    await invoke<ImageInventory>("transfer_wsl_image", { input: { distribution: source.target.distribution, image: inspectedImage.image, destination: target.target.destination } });
    imageTransferResult.textContent = `Transferred ${inspectedImage.image} to ${target.name}. Reconnect to verify Docker and provision Orcan on the remote host.`;
    finishJob(job, "succeeded", `Imported ${inspectedImage.image} on ${target.name}`);
  } catch (error) { imageTransferResult.textContent = `Transfer failed: ${String(error)}`; finishJob(job, "failed", String(error)); }
  finally { imageTransferRun.disabled = false; }
}

function renderEnclaves(): void {
  enclaveList.replaceChildren(...(profiles.length ? profiles.map((profile) => {
    const status = enclaveStatus.get(profile.id);
    const drafts = queuedChanges.filter((change) => change.enclave === enclaveChangeKey(profileConnection(profile))).length;
    const active = connected && current?.profileId === profile.id;
    const gear = actionButton("⚙", () => void openEnclaveSettings(profile), "secondary");
    gear.title = `Configure ${profile.name}`;
    gear.setAttribute("aria-label", `Configure ${profile.name}`);
    const actions: HTMLElement[] = [actionButton("Check Orcan", () => void checkEnclave(profile)), gear];
    if (!status?.report) actions.unshift(actionButton(needsStudioUpdate(status?.error ?? "") ? "Update Orcan" : "Provision Orcan", () => openProvisioning(profile), "secondary"));
    if (status?.report?.runtime.docker.container.state === "running") {
      actions.push(actionButton("Remove container", () => {
        current = profileConnection(profile);
        void runRuntimeAction("stop");
      }, "secondary"));
    }
    if (active) actions.push(el("span", { className: "badge", textContent: "Active" }));
    else actions.push(actionButton("Open", () => void openEnclave(profile), status?.state === "online" ? "" : "secondary"));
    const access = status?.report ? ` · ${accessExposure(status.report.runtime.launch)}` : "";
    const text = el("div", {}, el("strong", {}, dot(statusTone(status)), profile.name), el("span", { textContent: `${describeProfile(profile)} · ${statusText(status)}${access}${drafts ? ` · ${drafts} draft${drafts === 1 ? "" : "s"}` : ""}` }));
    if (status?.state === "offline") text.append(el("span", { className: "status-hint", textContent: failureHint(status.error ?? "") }));
    const item = el("div", { className: "list-item enclave-item" }, text, el("div", { className: "item-actions" }, ...actions));
    item.classList.toggle("active", active);
    return item;
  }) : [emptyState("Enclaves appear here once you create a profile.", "Create a profile", () => openProfileForm())]));
  renderCliProvision();
  renderOnlineProvision();
  renderImageTransfer();
  renderEnclaveCreator();
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
  const report = activeStatus?.report;
  const editable = canEditContext(report);
  const target = current?.target.kind === "wsl2" ? "WSL2" : current?.target.kind === "ssh" ? "SSH" : "Local";
  const access = report ? (editable ? "Editable" : "Read-only") : "Checking";
  activeLabel.textContent = connected && current ? `${current.label} · ${target} · ${access}` : profiles.length ? "Choose an Enclave" : "No Enclaves yet";
  activeInstance.title = report
    ? `${target} · ${report.host.user ?? "unknown user"} · ${report.context.configuration.path ?? `${report.paths.home}/orcan.config.json`} · ${editable ? "context changes available" : contextEditMessage()}`
    : "Open Enclaves to reconnect or edit this profile";
  const online = profiles.filter((profile) => enclaveStatus.get(profile.id)?.state === "online").length;
  const checking = profiles.some((profile) => enclaveStatus.get(profile.id)?.state === "checking");
  instanceState.textContent = profiles.length ? `${online} of ${profiles.length} Enclave${profiles.length === 1 ? "" : "s"} online${checking ? " · checking…" : ""}` : "No Enclaves yet";
}

function failureHint(error: string): string {
  if (needsStudioUpdate(error)) return "This Orcan CLI is older than Studio's control protocol. Select Update Orcan to update it in place; your profile, configuration, projects, and sandbox data stay untouched.";
  if (/execvpe\(orcan\).*no such file|orcan: not found|command not found/i.test(error)) return "Orcan CLI is not available on this target. Provision Orcan CLI first; Studio checks ~/.local/bin and the target PATH.";
  if (/host-key|known_hosts|Host key verification/i.test(error)) return "Open the profile and use Test connection. Studio will show the host fingerprint and can save your explicit trust decision.";
  if (/authentication|Permission denied|rejected/i.test(error)) return "The server rejected the sign-in. Check the user and the credential.";
  if (/no (password|key-passphrase) is stored/i.test(error)) return "The secret for this credential is missing from the vault. Edit the credential and enter it again.";
  if (/command not found|No such file|orcan: not found/i.test(error)) return "The machine was reached, but Orcan is not installed there or not on PATH.";
  if (/timed out|Connection refused|resolve|unreachable/i.test(error)) return "The machine could not be reached. Check the address, port, VPN, or Tailscale.";
  return "Adjust the details and test again; the Activity view keeps the full error.";
}

function needsStudioUpdate(error: string): boolean {
  return /unknown command:\s*studio|unknown command.*\bstudio\b/i.test(error);
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
    persistCachedReport(cacheKey(connection.target), report);
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
imageTransferInspect.addEventListener("click", () => void inspectTransferImage());
imageTransferRun.addEventListener("click", () => void transferImage());
onlineProvisionCheck.addEventListener("click", () => void checkOnlineProvision());
onlineProvisionRun.addEventListener("click", () => void provisionOnline());
onlineProvisionTarget.addEventListener("change", () => { onlineProvisionReadyProfileId = undefined; renderOnlineProvision(); });
imageTransferSource.addEventListener("change", () => { inspectedImage = undefined; imageTransferRun.disabled = true; });
imageTransferTarget.addEventListener("change", () => { imageTransferRun.disabled = true; });
imageTransferName.addEventListener("input", () => { inspectedImage = undefined; imageTransferRun.disabled = true; });
cliProvisionCheck.addEventListener("click", () => void checkCliProvision());
cliProvisionRun.addEventListener("click", () => void provisionCli());
for (const input of [cliProvisionSource, cliProvisionTarget, cliProvisionImage, cliProvisionImageName]) input.addEventListener("change", () => { cliProvisionReady = false; cliProvisionRun.disabled = true; });
cliProvisionImage.addEventListener("change", () => { cliProvisionImageField.hidden = !cliProvisionImage.checked; });
enclaveCreatePlan.addEventListener("click", () => void planEmptyEnclave());
enclaveCreateApply.addEventListener("click", () => { if (window.confirm("Create this empty Enclave?")) void planEmptyEnclave(true); });
for (const input of [enclaveCreateProfile, enclaveCreateGit, enclaveCreateDocker, enclaveCreateTtyd, enclaveCreateTtydAuth, enclaveCreateTtydUser, enclaveCreateTtydPassword]) input.addEventListener("change", () => { enclaveCreateApply.disabled = true; });
enclaveCreateTtyd.addEventListener("change", () => {
  enclaveCreateTtydAuth.disabled = !enclaveCreateTtyd.checked;
  if (!enclaveCreateTtyd.checked) enclaveCreateTtydAuth.checked = false;
  enclaveCreateTtydFields.hidden = !enclaveCreateTtyd.checked || !enclaveCreateTtydAuth.checked;
});
enclaveCreateTtydAuth.addEventListener("change", () => {
  enclaveCreateTtydFields.hidden = !enclaveCreateTtydAuth.checked;
  if (!enclaveCreateTtydAuth.checked) enclaveCreateTtydPassword.value = "";
});
$("#new-password-credential").addEventListener("click", () => openCredentialForm("password"));
$("#new-key-credential").addEventListener("click", () => openCredentialForm("private_key"));
$("#credential-back").addEventListener("click", () => leaveCredentialForm());
for (const input of document.querySelectorAll<HTMLInputElement>('input[name="location"]')) input.addEventListener("change", refreshProfileForm);
wslDistribution.addEventListener("change", () => void showWslDefaultUser());
credentialSelect.addEventListener("change", refreshProfileForm);
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
for (const item of navigationItems) item.addEventListener("click", () => showView(item.dataset.viewTarget ?? "overview"));
settingsRefresh.addEventListener("click", () => { if (current) void connect(current, settingsResult).catch(() => undefined); });
sandboxRefresh.addEventListener("click", () => { if (current) void connect(current, sandboxResult).catch(() => undefined); });
for (const [action, selector] of Object.entries(runtimeButtons)) document.querySelector<HTMLButtonElement>(selector)!.addEventListener("click", () => void runRuntimeAction(action as RuntimeAction));
settingsSync.addEventListener("click", async () => { if (!current || !canEditContext()) { settingsResult.textContent = contextEditMessage(); return; } const job = addJob("Orcan sync", current.label); settingsSync.disabled = true; settingsResult.textContent = "Reconciling Orcan context…"; try { await invoke("sync", { enclave: enclaveInput(current) }); settingsResult.textContent = "Sync completed. Restart is required only if Orcan reports a Compose-level change."; finishJob(job, "succeeded", "Context reconciled"); } catch (error) { settingsResult.textContent = `Sync failed: ${String(error)}`; finishJob(job, "failed", String(error)); } finally { settingsSync.disabled = false; } });
importParent.addEventListener("change", () => {
  importReady = false;
  importApplyButton.disabled = true;
  folderReady = false;
  folderApplyButton.disabled = true;
  importDestination.textContent = `Orcan will clone into ${importParent.options[importParent.selectedIndex]?.text ?? "the selected folder"}/<repository name>.`;
  importResult.textContent = "Preview the import before cloning.";
});
folderName.addEventListener("input", () => { folderReady = false; folderApplyButton.disabled = true; });
folderPlanButton.addEventListener("click", async () => {
  if (!current || !latestProbe || !snapshotRoot.textContent || snapshotRoot.textContent === "—") { folderResult.textContent = "Check an Enclave first."; return; }
  folderPlanButton.disabled = true;
  folderResult.textContent = "Checking folder plan…";
  try {
    const response = await invoke<{ plan: { destination: string; ready: boolean; blockers: string[] } }>("directory_plan", { enclave: enclaveInput(current), projectsRoot: snapshotRoot.textContent, parent: importParent.value, name: folderName.value.trim() });
    folderReady = response.plan.ready;
    folderApplyButton.disabled = !folderReady;
    folderResult.textContent = response.plan.ready ? `Ready: ${response.plan.destination}` : response.plan.blockers.join(" · ");
  } catch (error) { folderReady = false; folderApplyButton.disabled = true; folderResult.textContent = `Plan failed: ${String(error)}`; }
  finally { folderPlanButton.disabled = false; }
});
folderApplyButton.addEventListener("click", async () => {
  if (!folderReady || !current) return;
  folderApplyButton.disabled = true;
  const job = addJob("Create managed folder", folderName.value.trim());
  try {
    const response = await invoke<{ result: { path: string } }>("directory_apply", { enclave: enclaveInput(current), projectsRoot: snapshotRoot.textContent, parent: importParent.value, name: folderName.value.trim() });
    folderResult.textContent = `Created: ${response.result.path}`;
    folderName.value = "";
    folderReady = false;
    finishJob(job, "succeeded", response.result.path);
    await connect(current);
  } catch (error) { folderResult.textContent = `Create failed: ${String(error)}`; finishJob(job, "failed", String(error)); }
});
worktreeRepo.addEventListener("change", () => void refreshWorktreeBranches());
worktreeWorkspaces.addEventListener("change", renderWorktreeExisting);
worktreeBranch.addEventListener("input", () => {
  const exists = sourceBranches.includes(worktreeBranch.value.trim());
  worktreeReady = false;
  worktreeApply.disabled = true;
  if (exists) worktreeResult.textContent = `Existing branch: ${worktreeBranch.value.trim()}. The new worktree will check it out after you preview the plan.`;
  renderWorktreeBranchState();
});
branchSearch.addEventListener("input", renderBranchBrowser);
worktreeSourceUpdate.addEventListener("click", () => {
  const candidate = currentReport && parentCandidates(currentReport, parentRuns).find((item) => item.path === worktreeRepo.value);
  if (candidate) void updateProjectParent(candidate, "new worktree", candidate.name);
});
worktreePlan.addEventListener("click", async () => {
  if (!current) return;
  if (!canEditContext()) { worktreeResult.textContent = contextEditMessage(); return; }
  const workspaces = selectedWorkspaces();
  if (!worktreeRepo.value || !workspaces.length) {
    worktreeResult.textContent = "Choose a Git source and at least one workspace family.";
    return;
  }
  try {
    const response = await invoke<{ plan: { project?: string; destination: string; branch_exists?: boolean; ready: boolean; blockers: string[] } }>("worktree_plan", { enclave: enclaveInput(current), repo: worktreeRepo.value, branch: worktreeBranch.value, worktreesRoot: setting("setting-worktrees-root").textContent, workspaces });
    worktreeReady = response.plan.ready;
    worktreeApply.disabled = !worktreeReady;
    worktreeResult.textContent = response.plan.ready
      ? `Ready: ${response.plan.project ?? "worktree"} → ${response.plan.destination} · ${response.plan.branch_exists ? "check out the existing branch" : "create a new branch"} · attach to ${workspaces.join(", ")}.`
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
importPlanButton.addEventListener("click", async () => {
  if (!current || !latestProbe || !snapshotRoot.textContent || snapshotRoot.textContent === "—") { importResult.textContent = "Check an Enclave first."; return; }
  importPlanButton.disabled = true; importResult.textContent = "Building import plan…";
  try {
    const response = await invoke<{ plan: { destination: string; destination_state: string; ready: boolean; blockers: string[] } }>("import_plan", { enclave: enclaveInput(current), source: importSource.value, projectsRoot: snapshotRoot.textContent, parent: importParent.value || undefined });
    importReady = response.plan.ready; importApplyButton.disabled = !importReady;
    importResult.textContent = response.plan.ready ? `Ready: ${response.plan.destination} · ${response.plan.destination_state}` : response.plan.blockers.join(" · ");
  } catch (error) { importReady = false; importApplyButton.disabled = true; importResult.textContent = `Plan failed: ${String(error)}`; }
  finally { importPlanButton.disabled = false; }
});
importApplyButton.addEventListener("click", async () => {
  if (!importReady) return;
  importApplyButton.disabled = true; importResult.textContent = "Cloning repository…";
  const job = addJob("Repository import", importSource.value);
  try { const response = await invoke<{ result: { destination: string } }>("import_apply", { enclave: enclaveInput(current!), source: importSource.value, projectsRoot: snapshotRoot.textContent, parent: importParent.value || undefined }); importResult.textContent = `Imported: ${response.result.destination}`; importReady = false; finishJob(job, "succeeded", response.result.destination); }
  catch (error) { importResult.textContent = `Import failed: ${String(error)}`; finishJob(job, "failed", String(error)); }
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
void loadStore().catch((error) => {
  result.textContent = `Could not load saved Enclaves: ${String(error)}`;
});
