import { invoke } from "@tauri-apps/api/core";
import "./style.css";

type Target =
  | { kind: "local" }
  | { kind: "wsl2"; distribution: string }
  | { kind: "ssh"; destination: string };

type ProbeReport = {
  sandbox: { version: string };
  host: { os: string; architecture: string };
  capabilities: { docker: boolean; managed_projects: boolean; live_reconcile: boolean };
  runtime: { docker: { container: { state: string } } };
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
let worktreeReady = false;
let profiles: ConnectionProfile[] = [];
let activeProfileId: string | undefined;
let latestProbe = 0;
let storedKeyPassphrase = false;

function selectedTarget(): Target {
  if (transport.value === "local") return { kind: "local" };
  if (transport.value === "wsl2") return { kind: "wsl2", distribution: target.value };
  return { kind: "ssh", destination: target.value };
}

function cacheKey(targetValue: Target): string {
  return `orcan-studio:snapshot:${JSON.stringify(targetValue)}`;
}

function renderSnapshot(report: ProbeReport, cached = false): void {
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
  if (cached) result.textContent = "Showing the last known Sandbox snapshot. Refreshing will verify it.";
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
  const cached = localStorage.getItem(cacheKey(profile.target));
  if (cached) {
    try {
      renderSnapshot(JSON.parse(cached) as ProbeReport, true);
    } catch {
      localStorage.removeItem(cacheKey(profile.target));
    }
  }
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

transport.addEventListener("change", refreshTargetField);
sshAuth.addEventListener("change", refreshCredentials);
profilesSelect.addEventListener("change", () => {
  const profile = profiles.find((item) => item.id === profilesSelect.value);
  if (profile) applyProfile(profile);
  else activeProfileId = undefined;
  renderProfiles();
});
settingsRefresh.addEventListener("click", () => probeButton.click());
worktreePlan.addEventListener("click", async () => { try { const workspaces = worktreeWorkspaces.value.split(",").map((value) => value.trim()).filter(Boolean); const response = await invoke<{ plan: { destination: string; ready: boolean; blockers: string[] } }>("worktree_plan", { repo: worktreeRepo.value, branch: worktreeBranch.value, worktreesRoot: setting("setting-worktrees-root").textContent, workspaces }); worktreeReady = response.plan.ready; worktreeApply.disabled = !worktreeReady; worktreeResult.textContent = response.plan.ready ? `Ready: ${response.plan.destination} · ${workspaces.join(", ") || "no bindings"}` : response.plan.blockers.join(" · "); } catch (error) { worktreeReady = false; worktreeApply.disabled = true; worktreeResult.textContent = `Plan failed: ${String(error)}`; } });
worktreeApply.addEventListener("click", async () => { if (!worktreeReady) return; const workspaces = worktreeWorkspaces.value.split(",").map((value) => value.trim()).filter(Boolean); worktreeApply.disabled = true; worktreeResult.textContent = "Creating worktree…"; try { const response = await invoke<{ result: { path: string } }>("worktree_apply", { repo: worktreeRepo.value, branch: worktreeBranch.value, worktreesRoot: setting("setting-worktrees-root").textContent, workspaces }); worktreeResult.textContent = `Created: ${response.result.path}`; worktreeReady = false; } catch (error) { worktreeResult.textContent = `Create failed: ${String(error)}`; } });
cleanupPlan.addEventListener("click", async () => {
  try { const response = await invoke<{ plan: { ready: boolean; blockers: string[] } }>("worktree_cleanup", { path: cleanupPath.value, worktreesRoot: setting("setting-worktrees-root").textContent, apply: false }); cleanupApply.disabled = !response.plan.ready; cleanupResult.textContent = response.plan.ready ? "Plan ready. Type REMOVE to enable deletion." : response.plan.blockers.join(" · "); }
  catch (error) { cleanupResult.textContent = `Plan failed: ${String(error)}`; }
});
cleanupConfirm.addEventListener("input", () => { cleanupApply.disabled = cleanupConfirm.value !== "REMOVE"; });
cleanupApply.addEventListener("click", async () => { try { await invoke("worktree_cleanup", { path: cleanupPath.value, worktreesRoot: setting("setting-worktrees-root").textContent, apply: true }); cleanupResult.textContent = "Worktree removed."; cleanupApply.disabled = true; } catch (error) { cleanupResult.textContent = `Removal failed: ${String(error)}`; } });
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
  try { const response = await invoke<{ result: { destination: string } }>("import_apply", { source: importSource.value, projectsRoot: snapshotRoot.textContent, destination: importDestination.value || undefined }); importResult.textContent = `Imported: ${response.result.destination}`; importReady = false; }
  catch (error) { importResult.textContent = `Import failed: ${String(error)}`; }
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
  try {
    const report = await invoke<ProbeReport>("probe", { target: currentTarget, profileId: activeProfileId });
    if (request !== latestProbe) return;
    localStorage.setItem(cacheKey(currentTarget), JSON.stringify(report));
    renderSnapshot(report);
    result.textContent = `${report.host.os}/${report.host.architecture} · Orcan ${report.sandbox.version} · container ${report.runtime.docker.container.state}`;
  } catch (error) {
    if (request !== latestProbe) return;
    result.textContent = `Connection failed: ${String(error)}`;
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
  try { await invoke("parent_apply", { path: parentPath.value, branch: parentBranch.value, expectedHead: parentHead }); parentResult.textContent = "Parent updated."; }
  catch (error) { parentResult.textContent = `Update failed: ${String(error)}`; }
  finally { parentApplyButton.disabled = false; }
});

refreshTargetField();
refreshCredentials();
void loadProfiles().catch((error) => {
  result.textContent = `Could not load profiles: ${String(error)}`;
});
