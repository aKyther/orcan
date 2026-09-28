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
  paths: { projects_root: string };
  context: {
    workspaces: Array<{
      name: string;
      projects: Array<{ name?: string; path: string; kind: string; branch?: string; dirty?: boolean }>;
    }>;
    managed_projects: Array<{ path: string; kind: string }>;
    repositories: Array<{ repository_id: string; origin_url?: string; bindings: Array<{ workspace: string }> }>;
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

refreshTargetField();
refreshCredentials();
void loadProfiles().catch((error) => {
  result.textContent = `Could not load profiles: ${String(error)}`;
});
