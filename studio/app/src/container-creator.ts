import { actionButton, el } from "./dom";
import { confirmAction } from "./dialog";
import { enclaveInput } from "./transport";
import { creationBlocker, ownsEnclave } from "./enclave-model";
import type { identityPanel } from "./identities";
import type { Connection, ConnectionProfile, ProbeReport } from "./types";
import type { ServerCapacity } from "./server-model";

type Options = {
  invoke: <T>(command: string, args?: Record<string, unknown>) => Promise<T>;
  profiles: () => ConnectionProfile[];
  profileConnection: (profile: ConnectionProfile) => Connection;
  identityLibrary: ReturnType<typeof identityPanel>;
  showView: (name: string) => void;
  prepareProfile: (profile: ConnectionProfile, image?: boolean) => void;
  selectInstance: (profile: ConnectionProfile, instance: string) => void;
  observed: (profile: ConnectionProfile, connection: Connection, report: ProbeReport) => void;
  created: (profile: ConnectionProfile, connection: Connection) => Promise<void>;
  renderEnclaveStatus: () => void;
  failureHint: (error: string) => string;
  needsStudioUpdate: (error: string) => boolean;
  technicalDetail: (error: string) => HTMLElement;
};

/** Owns the complete creator form, readiness snapshot and plan invalidation. */
export function containerCreator(options: Options) {
  const $ = <T extends HTMLElement>(selector: string) => document.querySelector<T>(selector)!;
  const { invoke, profileConnection, identityLibrary, showView, prepareProfile, selectInstance, renderEnclaveStatus, failureHint, needsStudioUpdate, technicalDetail } = options;
  const selectedProfile = (select: HTMLSelectElement) => options.profiles().find(profile => profile.id === select.value);
  const enclaveCreateProfile = $<HTMLSelectElement>("#enclave-create-profile");
  const containerCreateImage = $<HTMLSelectElement>("#container-create-image");
  const containerCreateRoot = $<HTMLSelectElement>("#container-create-root");
  const containerCreatePaths = $("#container-create-paths");
  const enclaveCreateName = $<HTMLInputElement>("#enclave-create-name");
  const enclaveCreatePort = $<HTMLInputElement>("#enclave-create-port");
  const enclaveCreateCpus = $<HTMLInputElement>("#enclave-create-cpus");
  const enclaveCreateMemory = $<HTMLInputElement>("#enclave-create-memory");
  const enclaveCreateContainer = $("#enclave-create-container");
  const enclaveCreateCheck = $<HTMLButtonElement>("#enclave-create-check");
  const enclaveCreateReadiness = $("#enclave-create-readiness");
  const enclaveCreateOptions = $<HTMLFieldSetElement>("#enclave-create-options");
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
  type EnclaveReadiness = { user: string; docker: { available: boolean; version?: string; detail: string }; report?: ProbeReport; orcanError?: string; capacity?: ServerCapacity; images?: string[]; projectRoots?: string[] };
  let creatorReadiness: { connection: string; result: EnclaveReadiness } | undefined;
  let creatorBusy = false;
  let creatorRevision = 0;
  let creatorPlanRevision = -1;
  let creatorResourcesEdited = false;

  function creatorConnection(profile: ConnectionProfile): string {
    return JSON.stringify(enclaveInput(creatorProfileConnection(profile)));
  }

  function creatorProfileConnection(profile: ConnectionProfile): Connection {
    return { ...profileConnection(profile), instance: enclaveCreateName.value.trim() || undefined };
  }

  function creatorNameError(): string | undefined {
    const name = enclaveCreateName.value.trim();
    return name && !/^[a-z][a-z0-9-]{0,47}$/.test(name) ? "Use 1–48 lowercase letters, digits or hyphens; start with a letter." : undefined;
  }

  function creatorReport(profile: ConnectionProfile): ProbeReport | undefined {
    if (creatorReadiness?.connection !== creatorConnection(profile) || !creatorReadiness.result.docker.available || !creatorReadiness.result.report) return undefined;
    const report = structuredClone(creatorReadiness.result.report);
    if (report.runtime.docker.image && creatorReadiness.result.images?.length === 0) report.runtime.docker.image.present = false;
    if (containerCreateImage.value) report.runtime.docker.image = { name: containerCreateImage.value, present: Boolean(creatorReadiness.result.images?.includes(containerCreateImage.value)) };
    return report;
  }

  function creatorCanApply(profile: ConnectionProfile): boolean {
    return !creatorBusy && !creatorNameError() && creatorPlanRevision === creatorRevision && !creationBlocker(creatorReport(profile));
  }

  function openEnclaveCreator(profile?: ConnectionProfile, name?: string): void {
    if (creatorBusy) return;
    if (name !== undefined) { enclaveCreateName.value = name; creatorReadiness = undefined; }
    $("#server-browser").hidden = true;
    $("#enclave-creator").hidden = false;
    creatorPlanRevision = -1;
    creatorRevision += 1;
    renderEnclaveCreator();
    enclaveCreateProfile.value = profile?.id ?? "";
    showView("enclaves");
    renderEnclaveCreator();
    $("#enclave-creator").scrollIntoView({ block: "start" });
    enclaveCreateProfile.focus();
  }

  function closeEnclaveCreator(): void {
    if (creatorBusy) return;
    creatorPlanRevision = -1;
    creatorRevision += 1;
    enclaveCreateTtydPassword.value = "";
    creatorReadiness = undefined;
    enclaveCreateReadiness.textContent = "";
    enclaveCreateResult.textContent = "";
    $("#enclave-creator").hidden = true;
    $("#server-browser").hidden = false;
    $("#new-container").focus();
  }

  function renderEnclaveCreator(): void {
    $("#container-create-cancel").toggleAttribute("disabled", creatorBusy);
    if (creatorBusy) return;
    const previous = enclaveCreateProfile.value;
    enclaveCreateProfile.replaceChildren(
      new Option(options.profiles().length ? "Choose destination profile…" : "Create a profile first", ""),
      ...options.profiles().map((profile) => new Option(profile.name, profile.id)),
    );
    enclaveCreateProfile.value = options.profiles().some((profile) => profile.id === previous) ? previous : "";
    const profile = selectedProfile(enclaveCreateProfile);
    const ready = Boolean(profile && !creatorNameError() && !creationBlocker(creatorReport(profile)));
    enclaveCreateContainer.textContent = `Container: orcan-${enclaveCreateName.value.trim() || "1"} · shared sandbox and cache`;
    enclaveCreateCheck.disabled = !profile;
    enclaveCreateOptions.disabled = !ready;
    enclaveCreatePlan.disabled = !ready;
    enclaveCreateApply.disabled = !profile || !creatorCanApply(profile);
    const checked = profile && creatorReadiness?.connection === creatorConnection(profile);
    containerCreateImage.disabled = !checked || !creatorReadiness?.result.images?.length;
    containerCreateRoot.disabled = !checked || !creatorReadiness?.result.projectRoots?.length;
    if (!checked) {
      containerCreateImage.replaceChildren(new Option("Check destination first", ""));
      containerCreateRoot.replaceChildren(new Option("Reported by Orcan after checking", ""));
      containerCreatePaths.textContent = "Sandbox and cache are shared. Workspace metadata belongs to the named container.";
    }
    if (!profile) enclaveCreateReadiness.textContent = "Choose a profile. Orcan does not need to be installed yet.";
  }

  async function checkCreatorDestination(): Promise<void> {
    const profile = selectedProfile(enclaveCreateProfile);
    if (!profile || creatorBusy) return;
    if (creatorNameError()) { enclaveCreateResult.textContent = creatorNameError()!; return; }
    creatorBusy = true;
    $("#container-create-cancel").setAttribute("disabled", "");
    containerCreateImage.disabled = true;
    containerCreateRoot.disabled = true;
    identityLibrary.select.disabled = true;
    creatorPlanRevision = -1;
    creatorReadiness = undefined;
    enclaveCreateName.disabled = true;
    enclaveCreatePort.disabled = true;
    enclaveCreateCpus.disabled = true;
    enclaveCreateMemory.disabled = true;
    enclaveCreateProfile.disabled = true;
    enclaveCreateCheck.disabled = true;
    enclaveCreateOptions.disabled = true;
    enclaveCreatePlan.disabled = true;
    enclaveCreateApply.disabled = true;
    enclaveCreateReadiness.textContent = `Checking connection, Orcan, Docker and image on ${profile.name}…`;
    enclaveCreateResult.textContent = "";
    const connection = creatorConnection(profile);
    try {
      const readiness = await invoke<EnclaveReadiness>("enclave_readiness", { enclave: enclaveInput(creatorProfileConnection(profile)) });
      const selected = selectedProfile(enclaveCreateProfile);
      if (!selected || connection !== creatorConnection(selected)) return;
      creatorReadiness = { connection, result: readiness };
      const report = readiness.report;
      containerCreateImage.replaceChildren(...(readiness.images?.length ? readiness.images.map((image) => new Option(image, image)) : [new Option("No installed Orcan image — transfer one first", "")]));
      if (report?.runtime.docker.image && readiness.images?.includes(report.runtime.docker.image.name)) containerCreateImage.value = report.runtime.docker.image.name;
      containerCreateRoot.replaceChildren(...(readiness.projectRoots ?? []).map((root) => new Option(root, root)));
      if (readiness.projectRoots?.includes(report?.paths.projects_root ?? "")) containerCreateRoot.value = report!.paths.projects_root;
      if (report) containerCreatePaths.textContent = `Shared cache: ${report.paths.cache ?? "not reported — update Orcan CLI"} · Shared data: ${report.paths.data} · Container workspaces: ${report.paths.workspace_metadata_root}. Worktrees are scoped beneath the selected project root.`;
      const defaults = report?.runtime.defaults;
      if (!creatorResourcesEdited && defaults?.resources?.cpus) enclaveCreateCpus.value = String(defaults.resources.cpus);
      const memoryDefault = defaults?.resources?.memory?.match(/^(\d+)g$/i);
      if (!creatorResourcesEdited && memoryDefault) enclaveCreateMemory.value = memoryDefault[1];
      if (!creatorResourcesEdited && defaults?.ttyd?.host_port) enclaveCreatePort.value = String(defaults.ttyd.host_port);
      if (report) {
        options.observed(profile, creatorProfileConnection(profile), report);
      }
      const fact = (label: string, value: string, okay: boolean) => el("div", { className: `enclave-readiness-row ${okay ? "ready" : "attention"}` }, el("span", { textContent: okay ? "✓" : "!", ariaHidden: "true" }), el("strong", { textContent: label }), el("span", { textContent: value }));
      const image = report?.runtime.docker.image;
      enclaveCreateReadiness.replaceChildren(
        fact("Connection", `Signed in as ${readiness.user}`, true),
        fact("Orcan CLI", report ? report.sandbox.version : needsStudioUpdate(readiness.orcanError ?? "") ? "Update required" : "Not ready", Boolean(report)),
        fact("Docker", readiness.docker.available ? readiness.docker.version ?? "Ready" : "Not ready for this user", readiness.docker.available),
        fact("Default image", image ? `${image.name} · ${image.present ? "available" : "missing — choose an installed image above or transfer this one"}` : "Check after CLI installation", Boolean(image?.present)),
      );
      if (readiness.capacity?.memoryBytes) enclaveCreateReadiness.append(fact("VM capacity", `${readiness.capacity.cpus ?? "?"} CPUs · ${(readiness.capacity.memoryBytes / 1024 ** 3).toFixed(1)} GiB RAM total (not free capacity)${readiness.capacity.diskFreeBytes !== undefined ? ` · ${(readiness.capacity.diskFreeBytes / 1024 ** 3).toFixed(1)} GiB disk free` : ""}`, true));
      else if (readiness.capacity?.diskFreeBytes !== undefined) enclaveCreateReadiness.append(fact("Disk", `${(readiness.capacity.diskFreeBytes / 1024 ** 3).toFixed(1)} GiB free`, true));
      const actions = el("div", { className: "actions compact" });
      if (!report) actions.append(actionButton(needsStudioUpdate(readiness.orcanError ?? "") ? "Update CLI" : "Install CLI", () => prepareProfile(profile)));
      if (image && !image.present) actions.append(actionButton("Transfer image", () => prepareProfile(profile, true)));
      if (report && ownsEnclave(report)) actions.append(actionButton("Open existing container", () => selectInstance(profile, creatorProfileConnection(profile).instance ?? "")));
      enclaveCreateReadiness.append(actions);
      if (readiness.orcanError) enclaveCreateReadiness.append(technicalDetail(readiness.orcanError));
      if (!readiness.docker.available) enclaveCreateReadiness.append(el("p", { className: "muted", textContent: "Start Docker and grant this user access. On WSL2, enable Docker Desktop integration or prepare Docker Engine in this distribution." }), technicalDetail(readiness.docker.detail));
      enclaveCreateResult.textContent = creationBlocker(creatorReport(profile)) ?? "Ready. Review image, project root and access, then preview the plan.";
      renderEnclaveStatus();
    } catch (error) {
      enclaveCreateReadiness.replaceChildren(el("strong", { textContent: "Could not connect to this profile." }), el("span", { textContent: failureHint(String(error)) }), technicalDetail(String(error)));
    } finally {
      creatorBusy = false;
      identityLibrary.select.disabled = false;
      enclaveCreateName.disabled = false;
      enclaveCreatePort.disabled = false;
      enclaveCreateCpus.disabled = false;
      enclaveCreateMemory.disabled = false;
      enclaveCreateProfile.disabled = false;
      renderEnclaveCreator();
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
    if (creatorBusy || creatorNameError() || creationBlocker(creatorReport(profile)) || (apply && !creatorCanApply(profile))) {
      enclaveCreateResult.textContent = "Check the destination and preview the current plan before creating this container.";
      return;
    }
    const selectedIdentity = identityLibrary.selected();
    if (selectedIdentity && !creatorReport(profile)?.capabilities.identity_templates) { enclaveCreateResult.textContent = "Update the host Orcan CLI before using identity templates."; return; }
    const revision = creatorRevision;
    const connection = creatorProfileConnection(profile);
    const ttydHostPort = enclaveCreateTtyd.checked ? Number(enclaveCreatePort.value) : undefined;
    if (ttydHostPort !== undefined && (!Number.isInteger(ttydHostPort) || ttydHostPort < 1024 || ttydHostPort > 65535)) { enclaveCreateResult.textContent = "Choose a host port between 1024 and 65535."; return; }
    creatorBusy = true;
    $("#container-create-cancel").setAttribute("disabled", "");
    containerCreateImage.disabled = true;
    containerCreateRoot.disabled = true;
    identityLibrary.select.disabled = true;
    enclaveCreateName.disabled = true;
    enclaveCreatePort.disabled = true;
    enclaveCreateCpus.disabled = true;
    enclaveCreateMemory.disabled = true;
    enclaveCreateProfile.disabled = true;
    enclaveCreateCheck.disabled = true;
    enclaveCreateOptions.disabled = true;
    enclaveCreatePlan.disabled = true;
    enclaveCreateApply.disabled = true;
    enclaveCreateResult.textContent = apply ? "Creating empty container…" : "Reading creation plan…";
    try {
      const response = await invoke<{ plan?: { ready: boolean; changes: string[]; config: string } }>("enclave_action", {
        enclave: enclaveInput(connection),
        apply,
        ttydHostPort,
        cpus: Number(enclaveCreateCpus.value),
        memoryGb: Number(enclaveCreateMemory.value),
        image: containerCreateImage.value || undefined,
        projectsRoot: containerCreateRoot.value || undefined,
        identityId: selectedIdentity?.id,
        identityVersion: selectedIdentity?.version,
        withGit: enclaveCreateGit.checked,
        withDocker: enclaveCreateDocker.checked,
        withTtyd: enclaveCreateTtyd.checked,
        ttydCredential: enclaveTtydCredential(),
      });
      if (!apply && response.plan?.ready && revision === creatorRevision) {
        creatorPlanRevision = revision;
        enclaveCreateResult.replaceChildren(el("strong", { textContent: "Creation plan" }), el("ul", {}, ...response.plan.changes.map((change) => el("li", { textContent: change }))));
      }
      if (apply) {
        creatorPlanRevision = -1;
        enclaveCreateResult.textContent = "container created. Verifying and opening context…";
        enclaveCreateTtydPassword.value = "";
        await options.created(profile, connection);
        creatorReadiness = undefined;
        $("#enclave-creator").hidden = true;
        $("#server-browser").hidden = false;
        showView("contexts");
        enclaveCreateResult.textContent = "container is running. Add projects to its context.";
      }
    } catch (error) { creatorPlanRevision = -1; enclaveCreateResult.textContent = `container setup failed: ${String(error)}`; }
    finally { creatorBusy = false; identityLibrary.select.disabled = false; enclaveCreateName.disabled = false; enclaveCreatePort.disabled = false; enclaveCreateCpus.disabled = false; enclaveCreateMemory.disabled = false; enclaveCreateProfile.disabled = false; renderEnclaveCreator(); }
  }

  $("#new-container").addEventListener("click", () => openEnclaveCreator());
  $("#container-create-cancel").addEventListener("click", closeEnclaveCreator);
  enclaveCreatePlan.addEventListener("click", () => void planEmptyEnclave());
  enclaveCreateCheck.addEventListener("click", () => void checkCreatorDestination());
  enclaveCreateApply.addEventListener("click", async () => { if (await confirmAction("Create this container with the selected runtime access?", { title: "New container", confirmLabel: "Create" })) void planEmptyEnclave(true); });
  for (const input of [enclaveCreateProfile, enclaveCreateName, containerCreateImage, containerCreateRoot, enclaveCreatePort, enclaveCreateCpus, enclaveCreateMemory, enclaveCreateGit, enclaveCreateDocker, enclaveCreateTtyd, enclaveCreateTtydAuth, enclaveCreateTtydUser, enclaveCreateTtydPassword]) input.addEventListener("input", () => {
    if ([enclaveCreateCpus, enclaveCreateMemory, enclaveCreatePort].includes(input as HTMLInputElement)) creatorResourcesEdited = true;
    creatorRevision += 1;
    creatorPlanRevision = -1;
    if (input === enclaveCreateProfile || input === enclaveCreateName) { creatorReadiness = undefined; enclaveCreateReadiness.textContent = "Check this destination and container name before reviewing access options."; enclaveCreateResult.textContent = ""; }
    renderEnclaveCreator();
  });
  enclaveCreateTtyd.addEventListener("change", () => {
    enclaveCreateTtydAuth.disabled = !enclaveCreateTtyd.checked;
    if (!enclaveCreateTtyd.checked) enclaveCreateTtydAuth.checked = false;
    enclaveCreateTtydFields.hidden = !enclaveCreateTtyd.checked || !enclaveCreateTtydAuth.checked;
  });
  enclaveCreateTtydAuth.addEventListener("change", () => {
    enclaveCreateTtydFields.hidden = !enclaveCreateTtydAuth.checked;
    if (!enclaveCreateTtydAuth.checked) enclaveCreateTtydPassword.value = "";
  });

  function invalidate(): void { creatorRevision++; creatorPlanRevision = -1; renderEnclaveCreator(); }
  function replacement(profile: ConnectionProfile, instance: string, archive: string): void {
    if (creatorBusy) return;
    creatorReadiness = undefined;
    invalidate();
    openEnclaveCreator(profile, instance);
    enclaveCreateResult.textContent = `Previous configuration archived at ${archive}. Check the destination, select an identity and create the replacement.`;
  }
  return { open: openEnclaveCreator, check: checkCreatorDestination, render: renderEnclaveCreator, report: creatorReport, busy: () => creatorBusy, invalidate, replacement };
}
