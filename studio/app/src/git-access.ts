import { el } from "./dom";
import { confirmAction } from "./dialog";
import { withProvisionProgress, isProvisionRunning } from "./provision-progress";
import { enclaveInput } from "./transport";
import type { Connection, ConnectionProfile } from "./types";

type Key = { name: string; algorithm: string; fingerprint: string };
type Installed = { name: string; fingerprint: string; encrypted: boolean; configured: boolean; config: string };

/** Independent host preparation; no runtime/CLI requirement or secret in UI state. */
export function gitAccessPanel(invoke: <T>(command: string, args?: unknown) => Promise<T>, connection: (profile: ConnectionProfile) => Connection): { render: (profiles: ConnectionProfile[]) => void } {
  const select = (id: string) => document.querySelector<HTMLSelectElement>(`#git-access-${id}`)!;
  const input = (id: string) => document.querySelector<HTMLInputElement>(`#git-access-${id}`)!;
  const button = (id: string) => document.querySelector<HTMLButtonElement>(`#git-access-${id}`)!;
  const source = select("source"), destination = select("destination"), key = select("key");
  const name = input("name"), host = input("host"), user = input("user"), configure = input("configure");
  const list = button("list"), transfer = button("transfer"), test = button("test");
  const fingerprint = document.querySelector<HTMLElement>("#git-access-fingerprint")!;
  const result = document.querySelector<HTMLOutputElement>("#git-access-result")!;
  let profiles: ConnectionProfile[] = [];
  let keys: Key[] = [];
  let identity = "";
  let installed = "";
  let checking = false;
  const selected = (field: HTMLSelectElement) => profiles.find((profile) => profile.id === field.value);
  const descriptor = () => JSON.stringify([selected(source) && enclaveInput(connection(selected(source)!)), selected(destination) && enclaveInput(connection(selected(destination)!))]);
  const target = () => JSON.stringify([selected(destination) && enclaveInput(connection(selected(destination)!)), name.value, host.value]);
  const refresh = () => {
    const busy = checking || isProvisionRunning(result);
    list.disabled = busy || !selected(source) || !selected(destination) || source.value === destination.value;
    transfer.disabled = busy || identity !== descriptor() || !keys.some((item) => item.name === key.value) || !/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$/.test(name.value);
    test.disabled = busy || installed !== target();
  };
  const changed = () => { installed = ""; refresh(); };
  key.addEventListener("change", () => {
    const chosen = keys.find((item) => item.name === key.value);
    name.value = chosen?.name ?? "";
    fingerprint.textContent = chosen ? `${chosen.algorithm} · ${chosen.fingerprint}` : "Choose a source key";
    changed();
  });
  for (const field of [source, destination]) field.addEventListener("change", () => { identity = ""; keys = []; key.replaceChildren(new Option("Find keys first", "")); key.disabled = true; fingerprint.textContent = "Find keys for this source and destination."; changed(); });
  for (const field of [name, host, user, configure]) field.addEventListener("input", changed);
  list.addEventListener("click", async () => {
    if (list.disabled) return;
    const before = descriptor();
    checking = true; installed = ""; refresh();
    result.textContent = "Reading public key fingerprints; private keys are not exported…";
    try {
      const inventory = await invoke<{ keys: Key[] }>("git_ssh_keys", { enclave: enclaveInput(connection(selected(source)!)) });
      if (before !== descriptor()) return;
      keys = inventory.keys; identity = before;
      key.replaceChildren(...(keys.length ? keys.map((item) => new Option(`${item.name} · ${item.algorithm}`, item.name)) : [new Option("No transferable key/public-key pairs", "")]));
      key.disabled = !keys.length;
      key.dispatchEvent(new Event("change"));
      result.textContent = keys.length ? "Choose a key. Copy requires approval; collisions require a different destination name." : "No eligible pairs. Use an OpenSSH private key with a matching .pub file and private permissions. Hardware-backed keys cannot be copied.";
    } catch (error) { result.textContent = String(error); }
    finally { checking = false; refresh(); }
  });
  transfer.addEventListener("click", async () => {
    if (transfer.disabled) return;
    const chosen = keys.find((item) => item.name === key.value)!;
    const from = selected(source)!, to = selected(destination)!;
    const destinationIdentity = target();
    const before = JSON.stringify([descriptor(), key.value, name.value, host.value, user.value, configure.checked]);
    const approved = await confirmAction(`Copy private key ${chosen.name} (${chosen.fingerprint}) from ${from.name} to ${to.name} as ${name.value}? The destination gains this identity's Git permissions. A separate destination key is safer. ${configure.checked ? `Use it for ${host.value}, preserving existing SSH config bytes.` : "Keep existing SSH config unchanged."}`, { title: "Copy private SSH key", confirmLabel: "Copy key", danger: true });
    if (!approved || before !== JSON.stringify([descriptor(), key.value, name.value, host.value, user.value, configure.checked]) || transfer.disabled) return;
    try {
      const checked = await withProvisionProgress(result, `Git access: ${from.name} → ${to.name}`, (operationId) => invoke<Installed>("transfer_git_ssh_key", { operationId, input: { source: enclaveInput(connection(from)), destination: enclaveInput(connection(to)), sourceName: chosen.name, destinationName: name.value, fingerprint: chosen.fingerprint, host: host.value, user: user.value, configure: configure.checked, confirmed: true } }));
      installed = destinationIdentity;
      result.replaceChildren(el("strong", { textContent: `Installed ${checked.name} · ${checked.fingerprint}` }), el("span", { textContent: `${checked.configured ? "Selected Git host configured." : `Existing SSH config unchanged. Test config: ${checked.config}.`} ${checked.encrypted ? "Encrypted key preserved: unlock it on the destination before use." : ""} Start containers with Git access to expose the host SSH directory read-only.` }));
    } catch (error) { result.textContent = String(error); }
    finally { refresh(); }
  });
  test.addEventListener("click", async () => {
    if (test.disabled) return;
    checking = true; refresh(); result.textContent = "Testing Git SSH authentication without accepting host identities automatically…";
    const before = target();
    const endpoint = enclaveInput(connection(selected(destination)!));
    const selectedName = name.value, hostname = host.value;
    try {
      let checked = await invoke<{ ready: boolean; untrusted?: boolean; detail: string }>("test_git_ssh", { enclave: endpoint, name: selectedName, host: hostname });
      if (before !== target()) return;
      if (checked.untrusted) {
        const identity = await invoke<{ fingerprint: string; algorithm: string; key: string; changed: boolean }>("git_ssh_host_identity", { enclave: endpoint, host: hostname });
        if (before !== target()) return;
        if (identity.changed) { result.textContent = "Git host identity differs from an existing trusted entry. Studio did not replace it; verify the change with the administrator."; return; }
        const approved = await confirmAction(`Git host ${hostname} reports ${identity.algorithm} ${identity.fingerprint}. Verify this fingerprint with the Git service or its administrator: scanning alone does not prove identity. Save this identity on the destination and retry?`, { title: "Trust Git host identity", confirmLabel: "Trust and test" });
        if (!approved || before !== target()) return;
        await invoke("trust_git_ssh_host", { enclave: endpoint, host: hostname, fingerprint: identity.fingerprint, key: identity.key, confirmed: true });
        checked = await invoke("test_git_ssh", { enclave: endpoint, name: selectedName, host: hostname });
      }
      if (before !== target()) return;
      result.textContent = `${checked.ready ? "✓" : "!"} ${checked.detail}`;
    } catch (error) { result.textContent = String(error); }
    finally { checking = false; refresh(); }
  });
  return { render: (saved) => {
    profiles = saved;
    if (checking || isProvisionRunning(result)) return;
    for (const field of [source, destination]) {
      const previous = field.value;
      field.replaceChildren(new Option("Choose profile…", ""), ...profiles.map((profile) => new Option(profile.name, profile.id)));
      field.value = profiles.some((profile) => profile.id === previous) ? previous : "";
    }
    refresh();
  } };
}
