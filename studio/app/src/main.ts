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
type ConnectionProfile = { id: string; name: string; target: Target; ssh?: SshOptions };

const transport = document.querySelector<HTMLSelectElement>("#transport")!;
const target = document.querySelector<HTMLInputElement>("#target")!;
const targetLabel = document.querySelector<HTMLLabelElement>("#target-label")!;
const probeButton = document.querySelector<HTMLButtonElement>("#probe")!;
const saveProfileButton = document.querySelector<HTMLButtonElement>("#save-profile")!;
const deleteProfileButton = document.querySelector<HTMLButtonElement>("#delete-profile")!;
const result = document.querySelector<HTMLOutputElement>("#result")!;
const profileName = document.querySelector<HTMLInputElement>("#profile-name")!;
const profilesSelect = document.querySelector<HTMLSelectElement>("#profiles")!;
const sshUser = document.querySelector<HTMLInputElement>("#ssh-user")!;
const sshAuth = document.querySelector<HTMLSelectElement>("#ssh-auth")!;
const credentials = document.querySelector<HTMLDetailsElement>(".credentials")!;
const keyPath = document.querySelector<HTMLInputElement>("#key-path")!;
const keyPathLabel = document.querySelector<HTMLLabelElement>("#key-path-label")!;
const secret = document.querySelector<HTMLInputElement>("#secret")!;
const secretLabel = document.querySelector<HTMLLabelElement>("#secret-label")!;
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
let activeProfileId: string | undefined;
let latestProbe = 0;
let storedKeyPassphrase = false;
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

async function invoke<T>(command: string, _args?: unknown): Promise<T> {
  if (!demoMode) return tauriInvoke<T>(command, _args as never);
  await new Promise((resolve) => window.setTimeout(resolve, 180));
  const root = demoReport.paths.projects_root;
  const worktrees = demoReport.paths.managed_worktrees_root;
  const responses: Record<string, unknown> = {
    list_profiles: [{ id: "demo", name: "Demo Linux Sandbox", target: { kind: "local" } }],
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

function selectedTarget(): Target {
  if (transport.value === "local") return { kind: "local" };
  if (transport.value === "wsl2") return { kind: "wsl2", distribution: target.value };
  return { kind: "ssh", destination: target.value };
}

function cacheKey(targetValue: Target): string {
  return `orcan-studio:snapshot:${JSON.stringify(targetValue)}`;
}

function showView(name: string): void {
  const target = views.find((view) => view.dataset.view === name);
  if (!target || (name !== "overview" && !connected)) return;
  for (const view of views) view.hidden = view !== target;
  for (const item of navigationItems) {
    const active = item.dataset.viewTarget === name;
    item.classList.toggle("active", active);
    item.toggleAttribute("aria-current", active);
  }
  viewTitle.textContent = name[0].toUpperCase() + name.slice(1);
}

const healthPanel = document.querySelector<HTMLElement>(".health-panel")!;
const focusTitle = document.querySelector<HTMLElement>("#focus-title")!;
const initialFocus = { title: focusTitle.textContent, action: nextAction.textContent };
const needsManagedProjects = new Set(["repositories", "worktrees"]);

function lockStudio(): void {
  if (!connected) return;
  connected = false;
  showView("overview");
  for (const item of navigationItems.filter((item) => item.classList.contains("gated"))) item.hidden = true;
  healthPanel.hidden = true;
  snapshot.hidden = true;
  sandboxSettings.hidden = true;
  instanceState.textContent = "No Sandbox checked";
  activeInstance.textContent = "Connect an instance";
  focusTitle.textContent = initialFocus.title;
  nextAction.textContent = initialFocus.action;
}

function unlockStudio(report: ProbeReport): void {
  connected = true;
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
    : "The Sandbox is reachable, but its container is not running. Review its instance settings before changing context.";
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
  launchSummary.textContent = launch.recorded ? `Start/Restart reuse: ${flags.join(" · ")}` : "No recorded start flags — start this Sandbox once with orcan up on the instance.";
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
  if (action === "stop" && !window.confirm("Stop the Sandbox container? Running agent sessions will end.")) return;
  const label = action[0].toUpperCase() + action.slice(1);
  const job = addJob(`Sandbox ${action}`, transport.value);
  for (const selector of Object.values(runtimeButtons)) document.querySelector<HTMLButtonElement>(selector)!.disabled = true;
  runtimeResult.textContent = `${label} in progress…`;
  try {
    await invoke("runtime_action", { target: selectedTarget(), action });
    runtimeResult.textContent = `${label} finished. Refreshing instance…`;
    finishJob(job, "succeeded", label);
  } catch (error) {
    runtimeResult.textContent = `${label} failed: ${String(error)}`;
    finishJob(job, "failed", String(error));
  }
  probeButton.click();
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

function refreshTargetField(): void {
  const local = transport.value === "local";
  target.hidden = local;
  targetLabel.hidden = local;
  credentials.hidden = transport.value !== "ssh";
  if (transport.value === "wsl2") {
    targetLabel.textContent = "WSL2 distribution";
    target.placeholder = "Ubuntu-24.04";
  }
  if (transport.value === "ssh") {
    targetLabel.textContent = "SSH host or host:port";
    target.placeholder = "orcan-host:22";
  }
}

function refreshCredentials(): void {
  const password = sshAuth.value === "password";
  const privateKey = sshAuth.value === "private_key";
  keyPath.hidden = !privateKey;
  keyPathLabel.hidden = !privateKey;
  secret.hidden = !password && !privateKey;
  secretLabel.hidden = !password && !privateKey;
  secretLabel.textContent = privateKey ? "Key passphrase (optional)" : "SSH password";
}

function selectedAuthentication(): SshAuthentication | undefined {
  if (transport.value !== "ssh") return undefined;
  if (sshAuth.value === "password") return { kind: "password" };
  if (sshAuth.value === "private_key") {
    const path = keyPath.value.trim();
    if (!path) throw new Error("Enter the path to the private key.");
    return { kind: "private_key", path, has_passphrase: secret.value.length > 0 || storedKeyPassphrase };
  }
  return { kind: "agent" };
}

function applyProfile(profile: ConnectionProfile): void {
  activeProfileId = profile.id;
  profileName.value = profile.name;
  transport.value = profile.target.kind;
  sshUser.value = profile.ssh?.username ?? "";
  sshAuth.value = profile.ssh?.authentication.kind ?? "agent";
  keyPath.value = profile.ssh?.authentication.kind === "private_key" ? profile.ssh.authentication.path : "";
  storedKeyPassphrase = profile.ssh?.authentication.kind === "private_key" && profile.ssh.authentication.has_passphrase;
  secret.value = "";
  refreshCredentials();
  target.value = profile.target.kind === "local" ? "" : profile.target.kind === "wsl2" ? profile.target.distribution : profile.target.destination;
  refreshTargetField();
  result.textContent = "Profile selected. Check Sandbox to retrieve a current Orcan report.";
}

function renderProfiles(): void {
  profilesSelect.replaceChildren(new Option("No saved profile selected", ""));
  for (const profile of profiles) profilesSelect.add(new Option(profile.name, profile.id));
  profilesSelect.value = activeProfileId ?? "";
  deleteProfileButton.disabled = activeProfileId === undefined;
}

async function loadProfiles(): Promise<void> {
  profiles = await invoke<ConnectionProfile[]>("list_profiles");
  renderProfiles();
}

transport.addEventListener("change", () => { refreshTargetField(); lockStudio(); });
target.addEventListener("input", lockStudio);
sshAuth.addEventListener("change", refreshCredentials);
for (const item of navigationItems) item.addEventListener("click", () => showView(item.dataset.viewTarget ?? "overview"));
profilesSelect.addEventListener("change", () => {
  const profile = profiles.find((item) => item.id === profilesSelect.value);
  if (profile) applyProfile(profile);
  else activeProfileId = undefined;
  lockStudio();
  renderProfiles();
});
settingsRefresh.addEventListener("click", () => probeButton.click());
for (const [action, selector] of Object.entries(runtimeButtons)) document.querySelector<HTMLButtonElement>(selector)!.addEventListener("click", () => void runRuntimeAction(action as RuntimeAction));
settingsSync.addEventListener("click", async () => { const job = addJob("Orcan sync", transport.value); settingsSync.disabled = true; settingsResult.textContent = "Reconciling Orcan context…"; try { await invoke("sync", { target: selectedTarget() }); settingsResult.textContent = "Sync completed. Restart is required only if Orcan reports a Compose-level change."; finishJob(job, "succeeded", "Context reconciled"); } catch (error) { settingsResult.textContent = `Sync failed: ${String(error)}`; finishJob(job, "failed", String(error)); } finally { settingsSync.disabled = false; } });
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
  if (!latestProbe || !snapshotRoot.textContent || snapshotRoot.textContent === "—") { importResult.textContent = "Check a Sandbox first."; return; }
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
saveProfileButton.addEventListener("click", async () => {
  const name = profileName.value.trim();
  if (!name) {
    result.textContent = "Enter a profile name before saving.";
    return;
  }
  try {
    const authentication = selectedAuthentication();
    const profile: ConnectionProfile = {
      id: activeProfileId ?? crypto.randomUUID(),
      name,
      target: selectedTarget(),
      ...(authentication ? { ssh: { username: sshUser.value.trim() || undefined, authentication } } : {}),
    };
    await invoke("save_profile", { profile });
    if (secret.value) {
      const kind = authentication?.kind === "private_key" ? "key-passphrase" : "password";
      await invoke("save_secret", { profileId: profile.id, kind, secret: secret.value });
      if (kind === "key-passphrase") storedKeyPassphrase = true;
      secret.value = "";
    }
    activeProfileId = profile.id;
    await loadProfiles();
    result.textContent = `Saved profile: ${profile.name}`;
  } catch (error) {
    result.textContent = `Could not save profile: ${String(error)}`;
  }
});
deleteProfileButton.addEventListener("click", async () => {
  if (!activeProfileId) return;
  await invoke("delete_profile", { id: activeProfileId });
  activeProfileId = undefined;
  await loadProfiles();
  result.textContent = "Profile deleted.";
});
probeButton.addEventListener("click", async () => {
  const request = ++latestProbe;
  const currentTarget = selectedTarget();
  probeButton.disabled = true;
  probeButton.textContent = "Checking Sandbox…";
  result.textContent = "Connecting → reading Orcan context → checking runtime…";
  const job = addJob("Sandbox probe", "Connecting");
  try {
    const report = await invoke<ProbeReport>("probe", { target: currentTarget, profileId: activeProfileId });
    if (request !== latestProbe) return;
    localStorage.setItem(cacheKey(currentTarget), JSON.stringify(report));
    renderSnapshot(report);
    result.textContent = `${report.host.os}/${report.host.architecture} · Orcan ${report.sandbox.version} · container ${report.runtime.docker.container.state}`;
    finishJob(job, "succeeded", "Sandbox snapshot refreshed");
  } catch (error) {
    if (request !== latestProbe) return;
    lockStudio();
    result.textContent = `Connection failed: ${String(error)}`;
    finishJob(job, "failed", String(error));
  } finally {
    if (request === latestProbe) {
      probeButton.disabled = false;
      probeButton.textContent = "Refresh Sandbox";
    }
  }
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

refreshTargetField();
refreshCredentials();
renderJobs();
if (demoMode) {
  demoBanner.hidden = false;
  result.textContent = "UX preview ready. Check Sandbox loads representative sample data.";
}
void loadProfiles().catch((error) => {
  result.textContent = `Could not load profiles: ${String(error)}`;
});
