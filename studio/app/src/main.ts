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
      projects: Array<{ name?: string; path: string; kind: string; branch?: string; dirty?: boolean }>;
    }>;
    managed_projects: Array<{ path: string; kind: string }>;
    repositories: Array<{ repository_id: string; origin_url?: string; bindings: Array<{ workspace: string }> }>;
    configuration: { state: string; revision?: string };
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
const contextMap = document.querySelector<HTMLElement>("#context-map")!;
const parentPath = document.querySelector<HTMLInputElement>("#parent-path")!;
const parentBranch = document.querySelector<HTMLInputElement>("#parent-branch")!;
const parentPlanButton = document.querySelector<HTMLButtonElement>("#parent-plan")!;
const parentApplyButton = document.querySelector<HTMLButtonElement>("#parent-apply")!;
const parentResult = document.querySelector<HTMLOutputElement>("#parent-result")!;
let parentHead: string | undefined;
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
const activeInstance = document.querySelector<HTMLElement>("#active-instance")!;
const healthTitle = document.querySelector<HTMLElement>("#health-title")!;
const overviewRuntime = document.querySelector<HTMLElement>("#overview-runtime")!;
const overviewConfig = document.querySelector<HTMLElement>("#overview-config")!;
const overviewAgents = document.querySelector<HTMLElement>("#overview-agents")!;
const nextAction = document.querySelector<HTMLElement>("#next-action")!;
const settingsWorkspace = document.querySelector<HTMLInputElement>("#settings-workspace")!;
const settingsProject = document.querySelector<HTMLInputElement>("#settings-project")!;
const settingsProjectPlan = document.querySelector<HTMLButtonElement>("#settings-project-plan")!;
const settingsProjectApply = document.querySelector<HTMLButtonElement>("#settings-project-apply")!;
const settingsDetachPlan = document.querySelector<HTMLButtonElement>("#settings-detach-plan")!;
const settingsDetachApply = document.querySelector<HTMLButtonElement>("#settings-detach-apply")!;
let settingsProjectReady = false;
let settingsDetachReady = false;
const setting = (id: string) => document.querySelector<HTMLElement>(`#${id}`)!;
const cleanupPath = document.querySelector<HTMLInputElement>("#cleanup-path")!;
const cleanupConfirm = document.querySelector<HTMLInputElement>("#cleanup-confirm")!;
const cleanupPlan = document.querySelector<HTMLButtonElement>("#cleanup-plan")!;
const cleanupApply = document.querySelector<HTMLButtonElement>("#cleanup-apply")!;
const cleanupResult = document.querySelector<HTMLOutputElement>("#cleanup-result")!;
const worktreeRepo = document.querySelector<HTMLInputElement>("#worktree-repo")!;
const worktreeBranch = document.querySelector<HTMLInputElement>("#worktree-branch")!;
const worktreeWorkspaces = document.querySelector<HTMLInputElement>("#worktree-workspaces")!;
const worktreePlan = document.querySelector<HTMLButtonElement>("#worktree-plan")!;
const worktreeApply = document.querySelector<HTMLButtonElement>("#worktree-apply")!;
const worktreeResult = document.querySelector<HTMLOutputElement>("#worktree-result")!;
const jobsList = document.querySelector<HTMLElement>("#jobs-list")!;
type Job = { name: string; state: "running" | "succeeded" | "failed"; detail: string; at: string };
const jobs: Job[] = JSON.parse(localStorage.getItem("orcan-studio:jobs") ?? "[]");
function saveJobs(): void { localStorage.setItem("orcan-studio:jobs", JSON.stringify(jobs.slice(0, 50))); }
function addJob(name: string, detail: string): Job { const job = { name, detail, state: "running" as const, at: new Date().toISOString() }; jobs.unshift(job); saveJobs(); renderJobs(); return job; }
function finishJob(job: Job, state: "succeeded" | "failed", detail: string): void { job.state = state; job.detail = detail; saveJobs(); renderJobs(); }
function renderJobs(): void { jobsList.replaceChildren(...(jobs.length ? jobs.map((job) => { const row = document.createElement("div"); row.className = `job ${job.state}`; row.textContent = `${new Date(job.at).toLocaleString()} · ${job.name} · ${job.state} · ${job.detail}`; return row; }) : [Object.assign(document.createElement("p"), { className: "snapshot-shared", textContent: "No jobs yet." })])); }
let worktreeReady = false;
let profiles: ConnectionProfile[] = [];
let savedCredentials: Credential[] = [];
let current: Connection | undefined;
let latestProbe = 0;
let connected = false;
const demoMode = new URLSearchParams(window.location.search).has("demo");

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
    workspaces: [{ name: "platform", projects: [{ name: "api", path: "/home/orcan/.config/orcan/sandbox/api", kind: "git", branch: "main", dirty: false }, { name: "web", path: "/home/orcan/.config/orcan/sandbox/web", kind: "git", branch: "feature/studio", dirty: true }] }],
    managed_projects: [{ path: "/home/orcan/.config/orcan/sandbox/api", kind: "git" }, { path: "/home/orcan/.config/orcan/sandbox/web", kind: "git" }],
    repositories: [{ repository_id: "api", origin_url: "git@github.com:example/api.git", bindings: [{ workspace: "platform" }] }, { repository_id: "web", origin_url: "git@github.com:example/web.git", bindings: [{ workspace: "platform" }] }],
    configuration: { state: "synchronized", revision: "demo" },
  },
};

const demoStore: { profiles: ConnectionProfile[]; credentials: Credential[] } = {
  profiles: [{ id: "demo", name: "Demo workstation", target: { kind: "local" } }],
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

async function invoke<T>(command: string, _args?: unknown): Promise<T> {
  if (!demoMode) return tauriInvoke<T>(command, _args as never);
  await new Promise((resolve) => window.setTimeout(resolve, 180));
  if (/profile|credential/.test(command)) return demoStoreCommand(command, (_args ?? {}) as Record<string, unknown>) as T;
  const root = demoReport.paths.projects_root;
  const worktrees = demoReport.paths.managed_worktrees_root;
  const responses: Record<string, unknown> = {
    probe: demoReport,
    parent_plan: { plan: { head: "abc1234", ready: true, blockers: [] } },
    import_plan: { plan: { destination: `${root}/new-repository`, destination_state: "absent", ready: true, blockers: [] } },
    import_apply: { result: { destination: `${root}/new-repository` } },
    worktree_plan: { plan: { destination: `${worktrees}/api/feature-context`, ready: true, blockers: [] } },
    worktree_apply: { result: { path: `${worktrees}/api/feature-context` } },
    worktree_cleanup: { plan: { ready: true, blockers: [] } },
    settings_project_action: { plan: { ready: true, blockers: [] } },
    runtime_action: null,
  };
  return (responses[command] ?? {}) as T;
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

function showView(name: string): void {
  const target = views.find((view) => view.dataset.view === name);
  if (!target || (gatedViews.has(name) && !connected)) return;
  currentView = name;
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
  for (const item of navigationItems.filter((item) => item.classList.contains("gated"))) item.hidden = true;
  healthPanel.hidden = true;
  snapshot.hidden = true;
  sandboxSettings.hidden = true;
  instanceState.textContent = "Not connected";
  activeInstance.textContent = "Not connected";
  focusTitle.textContent = initialFocus.title;
  nextAction.textContent = initialFocus.action;
}

function unlockStudio(report: ProbeReport): void {
  connected = true;
  activeGroup.hidden = false;
  for (const item of navigationItems.filter((item) => item.classList.contains("gated"))) {
    item.hidden = needsManagedProjects.has(item.dataset.viewTarget ?? "") && !report.capabilities.managed_projects;
  }
  healthPanel.hidden = false;
  focusTitle.textContent = "Connected";
  const agents = Object.entries(report.runtime.docker.agents ?? {}).filter(([, available]) => available).map(([name]) => name);
  const label = `${report.host.os} · Orcan ${report.sandbox.version}`;
  instanceState.textContent = `Connected · ${report.runtime.docker.container.state}`;
  activeInstance.textContent = label;
  healthTitle.textContent = report.runtime.docker.container.state === "running" ? "Ready" : "Attention needed";
  overviewRuntime.textContent = report.runtime.docker.container.state;
  overviewConfig.textContent = report.context.configuration.state;
  overviewAgents.textContent = agents.length ? agents.join(", ") : "Not reported";
  nextAction.textContent = report.runtime.docker.container.state === "running"
    ? "Review the context map, then import a repository or create a worktree for the workspace family that needs it."
    : "The Enclave is reachable, but its container is not running. Review its instance settings before changing context.";
}

const launchSummary = document.querySelector<HTMLElement>("#launch-summary")!;
const launchWarning = document.querySelector<HTMLElement>("#launch-warning")!;
const runtimeResult = document.querySelector<HTMLOutputElement>("#runtime-result")!;
const runtimeButtons = { start: "#runtime-start", restart: "#runtime-restart", stop: "#runtime-stop" } as const;
type RuntimeAction = keyof typeof runtimeButtons;
let launch: NonNullable<ProbeReport["runtime"]["launch"]> = { recorded: false };

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
    await invoke("runtime_action", { target: current.target, action });
    runtimeResult.textContent = `${label} finished. Refreshing instance…`;
    finishJob(job, "succeeded", label);
  } catch (error) {
    runtimeResult.textContent = `${label} failed: ${String(error)}`;
    finishJob(job, "failed", String(error));
  }
  void connect(current);
}

function renderSnapshot(report: ProbeReport): void {
  snapshot.hidden = false;
  snapshotRoot.textContent = report.paths.projects_root;
  snapshotWorkspaces.textContent = String(report.context.workspaces.length);
  snapshotProjects.textContent = String(report.context.managed_projects.length);
  sandboxSettings.hidden = false;
  setting("setting-home").textContent = report.paths.home;
  setting("setting-data").textContent = report.paths.data;
  setting("setting-projects-root").textContent = report.paths.projects_root;
  setting("setting-workspaces-root").textContent = report.paths.workspace_metadata_root;
  setting("setting-worktrees-root").textContent = report.paths.managed_worktrees_root;
  setting("setting-config-state").textContent = report.context.configuration.revision ? `${report.context.configuration.state} · ${report.context.configuration.revision}` : report.context.configuration.state;
  const resources = report.runtime.resources;
  settingResources.textContent = resources ? `CPU ${resources.cpus ?? "—"} · RAM ${resources.memory ?? "—"} · SHM ${resources.shm_size ?? "—"}` : "Not reported";
  const agents = Object.entries(report.runtime.docker.agents ?? {}).filter(([, available]) => available).map(([name]) => name);
  settingAgents.textContent = agents.length ? agents.join(" · ") : "No image manifest reported";
  unlockStudio(report);
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
    const report = await invoke<ProbeReport>("probe", { target: connection.target, profileId: connection.profileId, credentialId: connection.credentialId, username: connection.username });
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
    await loadStore();
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

function lastSeen(profile: ConnectionProfile): string {
  try {
    const cached = localStorage.getItem(cacheKey(profile.target));
    if (!cached) return "Not checked yet";
    const report = JSON.parse(cached) as ProbeReport;
    return `Last seen: Orcan ${report.sandbox.version} · container ${report.runtime.docker.container.state}`;
  } catch { return "Not checked yet"; }
}

function renderEnclaves(): void {
  enclaveList.replaceChildren(...(profiles.length ? profiles.map((profile) => {
    const active = connected && current?.profileId === profile.id;
    const item = listItem(profile.name, `${describeProfile(profile)} · ${active ? "Connected" : lastSeen(profile)}`,
      actionButton(active ? "Refresh" : "Connect", () => void connect({ target: profile.target, label: profile.name, profileId: profile.id }).then((report) => { if (report) showView("overview"); }).catch(() => undefined), active ? "secondary" : ""));
    item.classList.toggle("active", active);
    return item;
  }) : [emptyState("Enclaves appear here once you create a profile.", "Create a profile", () => openProfileForm())]));
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
  renderEnclaves();
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
    const report = await invoke<ProbeReport>("probe", { target: connection.target, profileId: connection.profileId, credentialId: connection.credentialId, username: connection.username });
    if (request !== latestProbe) return undefined;
    localStorage.setItem(cacheKey(connection.target), JSON.stringify(report));
    current = connection;
    renderSnapshot(report);
    activeInstance.textContent = connection.label;
    activeGroup.textContent = `ACTIVE · ${connection.label.toUpperCase()}`;
    output.textContent = `Connected · ${report.host.os}/${report.host.architecture} · Orcan ${report.sandbox.version} · container ${report.runtime.docker.container.state}`;
    finishJob(job, "succeeded", "Enclave report refreshed");
    renderStore();
    return report;
  } catch (error) {
    if (request !== latestProbe) return undefined;
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
settingsSync.addEventListener("click", async () => { if (!current) return; const job = addJob("Orcan sync", current.label); settingsSync.disabled = true; settingsResult.textContent = "Reconciling Orcan context…"; try { await invoke("sync", { target: current.target }); settingsResult.textContent = "Sync completed. Restart is required only if Orcan reports a Compose-level change."; finishJob(job, "succeeded", "Context reconciled"); } catch (error) { settingsResult.textContent = `Sync failed: ${String(error)}`; finishJob(job, "failed", String(error)); } finally { settingsSync.disabled = false; } });
settingsProjectPlan.addEventListener("click", async () => { try { const response = await invoke<{ plan: { ready: boolean; blockers: string[] } }>("settings_project_action", { config: "orcan.config.json", workspace: settingsWorkspace.value, project: settingsProject.value, action: "attach", apply: false }); settingsProjectReady = response.plan.ready; settingsProjectApply.disabled = !settingsProjectReady; settingsResult.textContent = response.plan.ready ? "Attach plan ready; Orcan sync will be required." : response.plan.blockers.join(" · "); } catch (error) { settingsResult.textContent = `Plan failed: ${String(error)}`; } });
settingsProjectApply.addEventListener("click", async () => { if (!settingsProjectReady) return; const job = addJob("Project attach", settingsWorkspace.value); try { await invoke("settings_project_action", { config: "orcan.config.json", workspace: settingsWorkspace.value, project: settingsProject.value, action: "attach", apply: true }); settingsResult.textContent = "Project attached. Run orcan sync."; finishJob(job, "succeeded", settingsProject.value); settingsProjectApply.disabled = true; } catch (error) { settingsResult.textContent = `Attach failed: ${String(error)}`; finishJob(job, "failed", String(error)); } });
settingsDetachPlan.addEventListener("click", async () => { const response = await invoke<{ plan: { ready: boolean } }>("settings_project_action", { config: "orcan.config.json", workspace: settingsWorkspace.value, project: settingsProject.value, action: "detach", apply: false }); settingsDetachReady = response.plan.ready; settingsDetachApply.disabled = !settingsDetachReady; settingsResult.textContent = settingsDetachReady ? "Detach plan ready; files remain untouched." : "Detach blocked."; });
settingsDetachApply.addEventListener("click", async () => { if (!settingsDetachReady) return; const job = addJob("Project detach", settingsWorkspace.value); try { await invoke("settings_project_action", { config: "orcan.config.json", workspace: settingsWorkspace.value, project: settingsProject.value, action: "detach", apply: true }); finishJob(job, "succeeded", settingsProject.value); settingsResult.textContent = "Project detached. Run orcan sync."; } catch (error) { finishJob(job, "failed", String(error)); settingsResult.textContent = `Detach failed: ${String(error)}`; } });
worktreePlan.addEventListener("click", async () => { try { const workspaces = worktreeWorkspaces.value.split(",").map((value) => value.trim()).filter(Boolean); const response = await invoke<{ plan: { destination: string; ready: boolean; blockers: string[] } }>("worktree_plan", { repo: worktreeRepo.value, branch: worktreeBranch.value, worktreesRoot: setting("setting-worktrees-root").textContent, workspaces }); worktreeReady = response.plan.ready; worktreeApply.disabled = !worktreeReady; worktreeResult.textContent = response.plan.ready ? `Ready: ${response.plan.destination} · ${workspaces.join(", ") || "no bindings"}` : response.plan.blockers.join(" · "); } catch (error) { worktreeReady = false; worktreeApply.disabled = true; worktreeResult.textContent = `Plan failed: ${String(error)}`; } });
worktreeApply.addEventListener("click", async () => { if (!worktreeReady) return; const workspaces = worktreeWorkspaces.value.split(",").map((value) => value.trim()).filter(Boolean); worktreeApply.disabled = true; worktreeResult.textContent = "Creating worktree…"; const job = addJob("Worktree create", worktreeBranch.value); try { const response = await invoke<{ result: { path: string } }>("worktree_apply", { repo: worktreeRepo.value, branch: worktreeBranch.value, worktreesRoot: setting("setting-worktrees-root").textContent, workspaces }); worktreeResult.textContent = `Created: ${response.result.path}`; worktreeReady = false; finishJob(job, "succeeded", response.result.path); } catch (error) { worktreeResult.textContent = `Create failed: ${String(error)}`; finishJob(job, "failed", String(error)); } });
cleanupPlan.addEventListener("click", async () => {
  try { const response = await invoke<{ plan: { ready: boolean; blockers: string[] } }>("worktree_cleanup", { path: cleanupPath.value, worktreesRoot: setting("setting-worktrees-root").textContent, apply: false }); cleanupApply.disabled = !response.plan.ready; cleanupResult.textContent = response.plan.ready ? "Plan ready. Type REMOVE to enable deletion." : response.plan.blockers.join(" · "); }
  catch (error) { cleanupResult.textContent = `Plan failed: ${String(error)}`; }
});
cleanupConfirm.addEventListener("input", () => { cleanupApply.disabled = cleanupConfirm.value !== "REMOVE"; });
cleanupApply.addEventListener("click", async () => { const job = addJob("Worktree cleanup", cleanupPath.value); try { await invoke("worktree_cleanup", { path: cleanupPath.value, worktreesRoot: setting("setting-worktrees-root").textContent, apply: true }); cleanupResult.textContent = "Worktree removed."; cleanupApply.disabled = true; finishJob(job, "succeeded", cleanupPath.value); } catch (error) { cleanupResult.textContent = `Removal failed: ${String(error)}`; finishJob(job, "failed", String(error)); } });
importPlanButton.addEventListener("click", async () => {
  if (!latestProbe || !snapshotRoot.textContent || snapshotRoot.textContent === "—") { importResult.textContent = "Check an Enclave first."; return; }
  importPlanButton.disabled = true; importResult.textContent = "Building import plan…";
  try {
    const response = await invoke<{ plan: { destination: string; destination_state: string; ready: boolean; blockers: string[] } }>("import_plan", { source: importSource.value, projectsRoot: snapshotRoot.textContent, destination: importDestination.value || undefined });
    importReady = response.plan.ready; importApplyButton.disabled = !importReady;
    importResult.textContent = response.plan.ready ? `Ready: ${response.plan.destination} · ${response.plan.destination_state}` : response.plan.blockers.join(" · ");
  } catch (error) { importReady = false; importApplyButton.disabled = true; importResult.textContent = `Plan failed: ${String(error)}`; }
  finally { importPlanButton.disabled = false; }
});
importApplyButton.addEventListener("click", async () => {
  if (!importReady) return;
  importApplyButton.disabled = true; importResult.textContent = "Cloning repository…";
  const job = addJob("Repository import", importSource.value);
  try { const response = await invoke<{ result: { destination: string } }>("import_apply", { source: importSource.value, projectsRoot: snapshotRoot.textContent, destination: importDestination.value || undefined }); importResult.textContent = `Imported: ${response.result.destination}`; importReady = false; finishJob(job, "succeeded", response.result.destination); }
  catch (error) { importResult.textContent = `Import failed: ${String(error)}`; finishJob(job, "failed", String(error)); }
});
parentPlanButton.addEventListener("click", async () => {
  parentPlanButton.disabled = true; parentResult.textContent = "Checking parent repository…";
  try {
    const response = await invoke<{ plan: { head: string; ready: boolean; blockers: string[] } }>("parent_plan", { path: parentPath.value, branch: parentBranch.value });
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
  try { await invoke("parent_apply", { path: parentPath.value, branch: parentBranch.value, expectedHead: parentHead }); parentResult.textContent = "Parent updated."; finishJob(job, "succeeded", "Fast-forward applied"); }
  catch (error) { parentResult.textContent = `Update failed: ${String(error)}`; finishJob(job, "failed", String(error)); }
  finally { parentApplyButton.disabled = false; }
});

renderJobs();
if (demoMode) {
  demoBanner.hidden = false;
  result.textContent = "UX preview: every action below uses sample data.";
}
void loadStore().catch((error) => {
  result.textContent = `Could not load saved Enclaves: ${String(error)}`;
});
