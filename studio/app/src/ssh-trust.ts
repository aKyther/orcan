/** Explicit server trust, queued across concurrent UI operations. */
import type { SshHostKeyOffer } from "./types";

type Invoke = <T>(command: string, args?: unknown) => Promise<T>;
type Confirm = (message: string, options: { title: string; confirmLabel: string; danger: boolean }) => Promise<boolean>;

export function createSshTrust(invoke: Invoke, confirm: Confirm) {
  const pending = new Map<string, Promise<boolean>>();
  let queue: Promise<unknown> = Promise.resolve();
  return (destination: string, systemSsh: boolean): Promise<boolean> => {
    const key = `${systemSsh}:${destination}`;
    const existing = pending.get(key);
    if (existing) return existing;
    const task = queue.catch(() => undefined).then(async () => {
      const offer = await invoke<SshHostKeyOffer>("ssh_host_key", { destination, systemSsh });
      if (offer.status === "trusted") return true;
      const changed = offer.status === "changed";
      const warning = changed ? "The server key differs from the saved identity. Verify this fingerprint with the server owner before replacing it. Studio saves a backup of the previous known-hosts file." : "Approve this server’s identity to save it on this computer and continue. You can compare the fingerprint with the server owner.";
      if (!await confirm(`${offer.destination}\n\n${warning}\n\n${offer.algorithm}\n${offer.fingerprint}`, { title: changed ? "Server identity changed" : "First connection to this server", confirmLabel: changed ? "Replace identity and continue" : "Trust and continue", danger: changed })) return false;
      await invoke("trust_ssh_host_key", { destination, systemSsh, fingerprint: offer.fingerprint, replaceChanged: changed });
      return true;
    }).finally(() => pending.delete(key));
    pending.set(key, task);
    queue = task;
    return task;
  };
}
