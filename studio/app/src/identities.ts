import { actionButton, el } from "./dom";
import type { Identity } from "./types";

type Invoke = <T>(command: string, args?: Record<string, unknown>) => Promise<T>;

export function identityPanel(invoke: Invoke, changed: () => void) {
  const field = <T extends HTMLElement>(name: string) => document.querySelector<T>(`#identity-${name}`)!;
  const list = field<HTMLElement>("list");
  const name = field<HTMLInputElement>("name");
  const description = field<HTMLInputElement>("description");
  const instructions = field<HTMLTextAreaElement>("instructions");
  const status = field<HTMLOutputElement>("result");
  const save = field<HTMLButtonElement>("save");
  const fresh = field<HTMLButtonElement>("new");
  const cancel = field<HTMLButtonElement>("cancel");
  const editor = field<HTMLElement>("editor");
  const browser = field<HTMLElement>("browser");
  let returnFocus: HTMLElement | null = null;
  const select = document.querySelector<HTMLSelectElement>("#container-create-identity")!;
  let identities: Identity[] = [];
  let editing: Identity | undefined;
  let busy = false;
  let generation = 0;
  const revisions = new Map<string, Identity>();

  function edit(identity?: Identity) {
    if (busy) return;
    returnFocus = document.activeElement as HTMLElement | null;
    browser.hidden = true;
    editor.hidden = false;
    field<HTMLElement>("editor-title").textContent = identity ? "Edit identity" : "New identity";
    editing = identity;
    name.value = identity?.name ?? "";
    description.value = identity?.description ?? "";
    instructions.value = identity?.instructions ?? "";
    save.textContent = identity ? "Save new version" : "Create identity";
    status.textContent = identity ? `Editing ${identity.name} v${identity.version}. Existing containers keep their version.` : "Describe how this container's agents should work. Orcan base rules remain.";
    name.focus();
  }
  function closeEditor() {
    editing = undefined;
    name.value = description.value = instructions.value = "";
    editor.hidden = true;
    browser.hidden = false;
    (returnFocus?.isConnected ? returnFocus : fresh).focus();
  }
  cancel.addEventListener("click", () => {
    if (busy) return;
    closeEditor();
    status.textContent = "";
  });
  function render() {
    const previous = select.value;
    const choices = [...identities];
    const retained = revisions.get(previous);
    if (retained && !choices.some((identity) => identity.id === retained.id && identity.version === retained.version)) choices.push(retained);
    for (const identity of choices) revisions.set(`${identity.id}:${identity.version}`, identity);
    select.replaceChildren(new Option("Default — Orcan base rules", ""), ...choices.map((identity) => new Option(`${identity.name} · v${identity.version}`, `${identity.id}:${identity.version}`)));
    if ([...select.options].some((option) => option.value === previous)) select.value = previous;
    else if (previous) changed();
    list.replaceChildren(...identities.map((identity) => el("article", { className: "panel" },
      el("h3", { textContent: `${identity.name} · v${identity.version}` }),
      el("p", { textContent: identity.description }),
      el("details", {}, el("summary", { textContent: "View instructions" }), el("pre", { textContent: identity.instructions })),
      actionButton("Edit template", () => edit(identity), "secondary"))));
    if (!identities.length) list.append(el("p", { className: "hint", textContent: "No custom identities. Containers can use Default." }));
  }
  async function reload() {
    const request = ++generation;
    try {
      const response = await invoke<{ path: string; identities: Identity[] }>("list_identities");
      if (request !== generation) return;
      identities = response.identities;
      field<HTMLElement>("path").textContent = response.path;
      render();
    } catch (error) { if (request === generation) status.textContent = `Cannot load identity library: ${String(error)}`; }
  }
  fresh.addEventListener("click", () => { if (!busy) edit(); });
  field<HTMLButtonElement>("refresh").addEventListener("click", () => { if (!busy) void reload(); });
  field<HTMLButtonElement>("open-data").addEventListener("click", async () => {
    try { await invoke("open_studio_data"); } catch (error) { status.textContent = String(error); }
  });
  save.addEventListener("click", async () => {
    if (busy) return;
    busy = true;
    let saved = false;
    for (const input of [save, fresh, cancel, name, description, instructions]) input.disabled = true;
    try {
      const identity = await invoke<Identity>("save_identity", { id: editing?.id, expectedVersion: editing?.version, name: name.value, description: description.value, instructions: instructions.value });
      await reload();
      saved = true;
      changed();
      status.textContent = `${identity.name} v${identity.version} saved. Existing containers are unchanged.`;
    } catch (error) { status.textContent = `Could not save identity: ${String(error)}`; }
    finally {
      busy = false;
      for (const input of [save, fresh, cancel, name, description, instructions]) input.disabled = false;
      if (saved) closeEditor();
    }
  });
  select.addEventListener("change", changed);
  return { reload, selected: () => revisions.get(select.value), select };
}
