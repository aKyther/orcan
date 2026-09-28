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
};

type ConnectionProfile = { id: string; name: string; target: Target };

const transport = document.querySelector<HTMLSelectElement>("#transport")!;
const target = document.querySelector<HTMLInputElement>("#target")!;
const targetLabel = document.querySelector<HTMLLabelElement>("#target-label")!;
const probeButton = document.querySelector<HTMLButtonElement>("#probe")!;
const saveProfileButton = document.querySelector<HTMLButtonElement>("#save-profile")!;
const deleteProfileButton = document.querySelector<HTMLButtonElement>("#delete-profile")!;
const result = document.querySelector<HTMLOutputElement>("#result")!;
const profileName = document.querySelector<HTMLInputElement>("#profile-name")!;
const profilesSelect = document.querySelector<HTMLSelectElement>("#profiles")!;
let profiles: ConnectionProfile[] = [];
let activeProfileId: string | undefined;

function selectedTarget(): Target {
  if (transport.value === "local") return { kind: "local" };
  if (transport.value === "wsl2") return { kind: "wsl2", distribution: target.value };
  return { kind: "ssh", destination: target.value };
}

function refreshTargetField(): void {
  const local = transport.value === "local";
  target.hidden = local;
  targetLabel.hidden = local;
  if (transport.value === "wsl2") {
    targetLabel.textContent = "WSL2 distribution";
    target.placeholder = "Ubuntu-24.04";
  }
  if (transport.value === "ssh") {
    targetLabel.textContent = "SSH destination";
    target.placeholder = "orcan-host";
  }
}

function applyProfile(profile: ConnectionProfile): void {
  activeProfileId = profile.id;
  profileName.value = profile.name;
  transport.value = profile.target.kind;
  target.value = profile.target.kind === "local" ? "" : profile.target.kind === "wsl2" ? profile.target.distribution : profile.target.destination;
  refreshTargetField();
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
  const profile: ConnectionProfile = {
    id: activeProfileId ?? crypto.randomUUID(),
    name,
    target: selectedTarget(),
  };
  try {
    await invoke("save_profile", { profile });
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
  probeButton.disabled = true;
  result.textContent = "Checking Sandbox…";
  try {
    const report = await invoke<ProbeReport>("probe", { target: selectedTarget() });
    result.textContent = `${report.host.os}/${report.host.architecture} · Orcan ${report.sandbox.version} · container ${report.runtime.docker.container.state}`;
  } catch (error) {
    result.textContent = `Connection failed: ${String(error)}`;
  } finally {
    probeButton.disabled = false;
  }
});

refreshTargetField();
void loadProfiles().catch((error) => {
  result.textContent = `Could not load profiles: ${String(error)}`;
});
