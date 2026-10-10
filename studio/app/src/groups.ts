import { actionButton, el } from "./dom";
import { confirmAction } from "./dialog";
import { enclaveCanvas } from "./enclave-canvas";
import { targetMatches, type Group, type GroupMember } from "./group-model";
import type { ProbeReport, Target } from "./types";

type Profile = { id: string; name: string; target: Target };
type Invoke = <T>(command: string, args?: unknown) => Promise<T>;
export function groupPanel(invoke: Invoke, profiles: () => Profile[], connection: (profileId: string, instance?: string) => unknown, launcher: () => string) {
  const field = <T extends HTMLElement>(id: string) => document.querySelector<T>(`#group-${id}`)!;
  const name = field<HTMLInputElement>("name"), profile = field<HTMLSelectElement>("profile"), instance = field<HTMLSelectElement>("instance");
  const result = field<HTMLOutputElement>("result");
  let groups: Group[] = [], group: Group;
  let dirty = false, busy = false, inventoryGeneration = 0;
  let inspected: GroupMember | undefined;
  const canvas = enclaveCanvas(field("canvas"), markDirty, (kind, member, workspace) => { void operate(kind, member, workspace); }, inspect);
  function markDirty() { dirty = true; field("state").textContent = "Unsaved layout"; }
  function inspect(member: GroupMember) {
    inspected = member;
    const state = canvas.state(member.container_id);
    const report = state?.report;
    field("details").replaceChildren(el("h3", { textContent: member.label }), el("p", { textContent: state?.error ?? "Check status before Start or Attach." }), ...[
      ["Host UUID", member.host_id], ["Container UUID", member.container_id], ["Profile", profiles().find((p) => p.id === member.profile_id)?.name ?? "Missing profile"],
      ["Identity", report?.context.identity ? `${report.context.identity.name} · v${report.context.identity.version}` : report ? "Default" : "Not checked"],
      ["Projects", report?.paths.projects_root ?? "Not checked"],
    ].map(([label, value]) => el("p", {}, el("strong", { textContent: label }), el("code", { textContent: value }))));
  }
  function setGroup(value: Group, keepStates = false) {
    group = structuredClone(value); name.value = group.name; dirty = false;
    canvas.setGroup(group, keepStates); inspected = undefined;
    field("details").textContent = "Select a container card to inspect its UUIDs and checked state.";
    field("state").textContent = group.revision ? `Saved · revision ${group.revision}` : "New enclave";
    field("editor-title").textContent = group.revision ? group.name : "New enclave";
    renderList();
  }
  function renderList() {
    field("list").replaceChildren(...(groups.length ? groups.map((item) => {
      const hosts = new Set(item.members.map((member) => member.host_id)).size;
      return el("article", { className: "enclave-library-card" },
        el("header", {}, el("h3", { textContent: item.name, title: item.name }), actionButton("Open", () => { void openEditor(item); }, "secondary")),
        el("p", { textContent: `${item.members.length} container${item.members.length === 1 ? "" : "s"} · ${hosts} server${hosts === 1 ? "" : "s"}` }));
    }) : [el("p", { className: "hint", textContent: "No enclaves yet. Use New enclave to group existing containers from your servers." })]));
  }
  async function openEditor(saved?: Group) {
    if (busy || !await discard()) return;
    field("browser").hidden = true;
    field("editor").hidden = false;
    result.textContent = "";
    setGroup(saved ?? { id: crypto.randomUUID(), revision: 0, name: "", members: [], edges: [] });
    name.focus();
  }
  async function closeEditor() {
    if (busy || !await discard()) return;
    setGroup({ id: crypto.randomUUID(), revision: 0, name: "", members: [], edges: [] });
    field("editor").hidden = true;
    field("browser").hidden = false;
    result.textContent = "";
    field("new").focus();
  }
  async function discard(): Promise<boolean> { return !dirty || await confirmAction("Discard unsaved enclave layout changes?", { title: "Unsaved enclave", confirmLabel: "Discard changes", danger: true }); }
  function endpoint(member: GroupMember) { return connection(member.profile_id, member.instance ?? undefined); }
  async function run(operation: () => Promise<void>) {
    if (busy) return;
    busy = true; canvas.setBusy(true);
    const controls = [...document.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLButtonElement>('[data-view="groups"] input, [data-view="groups"] select, [data-view="groups"] button')].filter((control) => !control.closest("#group-canvas"));
    controls.forEach((control) => control.disabled = true);
    try { await operation(); } catch (error) { result.textContent = String(error); }
    finally { busy = false; canvas.setBusy(false); controls.filter((control) => !control.closest("#group-canvas")).forEach((control) => control.disabled = false); }
  }
  async function operate(kind: "check" | "start" | "attach", member: GroupMember, workspace?: string) {
    await run(async () => {
      canvas.setState(member.container_id, { state: "checking" });
      try {
        const args = { enclave: endpoint(member), hostId: member.host_id, containerId: member.container_id };
        const report = await invoke<ProbeReport>(kind === "start" ? "group_start" : "group_probe", args);
        if (!targetMatches(report, member)) throw new Error("Target identity mismatch. No operation authorized.");
        canvas.setState(member.container_id, { state: "ready", report });
        if (kind === "attach") {
          if (report.runtime.docker.container.state !== "running" || !report.context.workspaces.some((ws) => ws.name === workspace)) throw new Error("Select an existing workspace in a running container.");
          await invoke("open_terminal", { ...args, workspace, launcher: launcher() });
          result.textContent = `Opened ${member.label} · ${workspace}. Agent sign-in is manual.`;
        } else result.textContent = `${member.label}: ${report.runtime.docker.container.state}`;
      } catch (error) {
        const detail = String(error);
        canvas.setState(member.container_id, { state: /identity|UUID|fingerprint|configuration/i.test(detail) ? "mismatch" : "offline", error: detail });
        throw error;
      } finally { if (inspected?.container_id === member.container_id) inspect(member); }
    });
  }
  async function refresh(reloadCurrent = false) {
    const old = profile.value;
    profile.replaceChildren(...profiles().map((item) => new Option(item.name, item.id)));
    if (profiles().some((item) => item.id === old)) profile.value = old;
    if (busy) return;
    await run(async () => {
      groups = await invoke<Group[]>("list_groups");
      if (reloadCurrent && group.revision) {
        const saved = groups.find((item) => item.id === group.id);
        if (!saved) throw new Error("Saved enclave was removed. Create a new enclave explicitly; its containers are unchanged.");
        setGroup(saved);
      } else if (reloadCurrent) setGroup({ id: crypto.randomUUID(), revision: 0, name: "", members: [], edges: [] });
      else renderList();
    });
  }
  async function inventory() {
    const chosen = profile.value, request = ++inventoryGeneration;
    instance.replaceChildren();
    if (!chosen) return;
    await run(async () => {
      const report = await invoke<{ instances: Array<{ instance: string | null; container: string }> }>("list_instances", { enclave: connection(chosen) });
      if (request !== inventoryGeneration || profile.value !== chosen) return;
      instance.replaceChildren(...report.instances.map((item) => new Option(item.container, item.instance ?? "")));
      result.textContent = "Select an existing container. Add registers UUIDs when needed; it never creates or starts a runtime.";
    });
  }
  name.addEventListener("input", () => { group.name = name.value; markDirty(); });
  field("new").addEventListener("click", () => { void openEditor(); });
  field("back").addEventListener("click", () => { void closeEditor(); });
  field("refresh").addEventListener("click", () => { if (!busy) void refresh(); });
  field("reload").addEventListener("click", async () => { if (!busy && await discard()) void refresh(true); });
  field("inventory").addEventListener("click", () => { void inventory(); });
  profile.addEventListener("change", () => { inventoryGeneration++; instance.replaceChildren(); });
  field("add").addEventListener("click", () => { void run(async () => {
    if (!profile.value || !instance.options.length) throw new Error("Choose a server and check its container list first.");
    const selected = profiles().find((item) => item.id === profile.value)!;
    const report = await invoke<ProbeReport>("register_target", { enclave: connection(selected.id, instance.value || undefined) });
    if (report.target?.state !== "ready" || !report.target.host_id || !report.target.container_id) throw new Error(report.target?.reason ?? "Container registration failed");
    if (group.members.some((member) => member.container_id === report.target!.container_id)) throw new Error("This container is already in the enclave.");
    const member: GroupMember = { host_id: report.target.host_id, container_id: report.target.container_id, profile_id: selected.id, instance: instance.value || null, label: `${selected.name} · ${report.runtime.docker.container.name}`, x: (group.members.length % 3) * 360, y: Math.floor(group.members.length / 3) * 300 };
    group.members.push(member); canvas.sync(); canvas.setState(member.container_id, { state: "ready", report }); markDirty(); inspect(member);
    result.textContent = "Container added. Save the enclave to keep its membership and layout.";
  }); });
  field("save").addEventListener("click", () => { void run(async () => {
    const saved = await invoke<Group>("save_group", { group });
    groups = groups.filter((item) => item.id !== saved.id); groups.push(saved); setGroup(saved, true);
    result.textContent = "Enclave saved. Saving and visual lines execute no work.";
  }); });
  field("open-data").addEventListener("click", () => { void run(async () => { await invoke("open_studio_data"); }); });
  setGroup({ id: crypto.randomUUID(), revision: 0, name: "", members: [], edges: [] });
  return { refresh };
}
