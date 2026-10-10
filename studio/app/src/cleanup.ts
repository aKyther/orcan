import { actionButton, el } from "./dom";
import { confirmAction } from "./dialog";

type Profile = { id: string; name: string };
type Invoke = <T>(command: string, args?: unknown) => Promise<T>;
type Inventory = {
  cli: { path: string | null; version: string | null; removable: boolean; reason: string };
  images: Array<{ image: string; id: string; size: number; containers: string[] }>;
  dockerError: string | null;
};

export function cleanupPanel(invoke: Invoke, profiles: () => Profile[], connection: (id: string) => unknown, changed: (id: string) => void) {
  const target = document.querySelector<HTMLSelectElement>("#server-cleanup-server")!;
  const check = document.querySelector<HTMLButtonElement>("#server-cleanup-check")!;
  const list = document.querySelector<HTMLElement>("#server-cleanup-installed")!;
  const result = document.querySelector<HTMLOutputElement>("#server-cleanup-result")!;
  let busy = false, generation = 0;
  function clear() { generation++; list.replaceChildren(); result.textContent = "Check the server to list its installed CLI and Orcan images."; }
  function syncProfiles() {
    const previous = target.value;
    target.replaceChildren(new Option("Choose server…", ""), ...profiles().map(profile => new Option(profile.name, profile.id)));
    target.value = profiles().some(profile => profile.id === previous) ? previous : "";
    if (target.value !== previous) clear();
    check.disabled = busy || !target.value;
  }
  function endpoint(id: string, snapshot: string) {
    if (target.value !== id || JSON.stringify(connection(id)) !== snapshot) throw new Error("Server selection changed. Check the server again.");
    return connection(id);
  }
  async function remove(id: string, snapshot: string, command: string, args: unknown, message: string, title: string) {
    if (busy) return;
    try {
      endpoint(id, snapshot);
      if (!await confirmAction(message, { title, confirmLabel: "Remove", danger: true })) return;
      const enclave = endpoint(id, snapshot);
      busy = true;
      target.disabled = check.disabled = true;
      list.querySelectorAll<HTMLButtonElement>("button").forEach(button => button.disabled = true);
      result.textContent = "Removing selected installation…";
      await invoke(command, { ...args as Record<string, unknown>, enclave, confirmed: true });
      changed(id);
      list.replaceChildren();
      result.textContent = "Removed. Configuration, projects and containers were kept. Check the server again to refresh its installation list.";
    } catch (error) { list.replaceChildren(); result.textContent = `Removal failed: ${String(error)}. Check the server again.`; }
    finally { busy = false; target.disabled = false; check.disabled = !target.value; }
  }
  async function inspect() {
    if (busy || !target.value) return;
    const id = target.value;
    const profile = profiles().find(profile => profile.id === id)!;
    const enclave = connection(id), snapshot = JSON.stringify(enclave);
    const request = ++generation;
    busy = true; target.disabled = check.disabled = true;
    list.replaceChildren(); result.textContent = "Checking installed CLI and Orcan images…";
    try {
      const installed = await invoke<Inventory>("server_cleanup_inventory", { enclave });
      if (request !== generation) return;
      endpoint(id, snapshot);
      const cli = installed.cli;
      const removeCli = actionButton("Remove CLI", () => void remove(id, snapshot, "remove_server_cli", { expectedPath: cli.path, expectedVersion: cli.version }, `Remove Orcan CLI ${cli.version} from ${profile.name}?\n${cli.path}\n\nCLI launcher and managed installation files will be removed. All containers, images, configuration and projects will remain.`, "Remove Orcan CLI"), "secondary");
      removeCli.disabled = !cli.removable;
      list.append(el("article", { className: "list-item" }, el("div", {}, el("strong", { textContent: cli.version ?? "CLI not installed" }), el("span", { textContent: cli.path ?? "" }), ...(cli.reason ? [el("p", { className: "hint", textContent: cli.reason })] : [])), removeCli));
      for (const image of installed.images) {
        const button = actionButton("Remove image", () => void remove(id, snapshot, "remove_destination_image", { image: image.image, expectedId: image.id }, `Remove ${image.image} from ${profile.name}?\n\nOnly this image tag will be removed. CLI, configuration and projects will remain. Images in use cannot be removed.`, "Remove Orcan image"), "secondary");
        button.disabled = image.containers.length > 0;
        list.append(el("article", { className: "list-item" }, el("div", {}, el("strong", { textContent: image.image }), el("span", { textContent: `${Math.round(image.size / 1024 ** 2)} MiB · ${image.containers.length ? `Used by: ${image.containers.join(", ")}` : "Not used by any container"}` })), button));
      }
      if (installed.dockerError) list.append(el("p", { className: "hint", textContent: `Could not check Docker images: ${installed.dockerError}. CLI removal is independent of Docker.` }));
      else if (!installed.images.length) list.append(el("p", { className: "hint", textContent: "No installed images labelled Orcan." }));
      result.textContent = "Choose exactly what to remove. Each removal needs confirmation.";
    } catch (error) { result.textContent = `Could not check server: ${String(error)}`; }
    finally { busy = false; target.disabled = false; check.disabled = !target.value; }
  }
  target.addEventListener("change", () => { clear(); check.disabled = !target.value; });
  check.addEventListener("click", () => void inspect());
  syncProfiles();
  return { syncProfiles };
}
