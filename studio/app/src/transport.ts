import { invoke as tauriInvoke } from "@tauri-apps/api/core";
import type { Connection, ConnectionProfile, Target } from "./types";

export const demoMode = new URLSearchParams(window.location.search).has("demo") || !("__TAURI_INTERNALS__" in window);

export function invokeTauri<T>(command: string, args?: unknown): Promise<T> {
  return tauriInvoke<T>(command, args as never);
}

type Endpoint = ReturnType<typeof enclaveInput>;

export function createTrustedInvoker(
  invoke: typeof invokeTauri, profiles: () => ConnectionProfile[],
  trust: (destination: string, systemSsh: boolean) => Promise<boolean>,
) {
  return async <T>(command: string, input?: unknown): Promise<T> => {
    const args = input as { enclave?: Endpoint; input?: { source?: Endpoint; destination?: string | Endpoint; destinationProfileId?: string; destinationCredentialId?: string } } | undefined;
    const destination = args?.input?.destination;
    const endpoints = [args?.enclave, args?.input?.source,
      typeof destination === "object" ? destination : typeof destination === "string" ? {
        target: { kind: "ssh" as const, destination }, profileId: args?.input?.destinationProfileId,
        credentialId: args?.input?.destinationCredentialId,
      } : undefined];
    const checked = new Set<string>();
    for (const endpoint of endpoints) {
      if (endpoint?.target.kind !== "ssh") continue;
      const profile = profiles().find(item => item.id === endpoint.profileId);
      const credential = endpoint.credentialId ?? profile?.credential_id;
      const system = !credential && (!profile?.ssh || profile.ssh.authentication.kind === "agent");
      const key = `${system}:${endpoint.target.destination}`;
      if (checked.has(key)) continue;
      if (!await trust(endpoint.target.destination, system)) throw new Error("Server identity was not approved. No connection was made.");
      checked.add(key);
    }
    return invoke<T>(command, input);
  };
}

/** The minimal connection descriptor accepted by the native Studio commands. */
export function enclaveInput(connection: Connection): { target: Target; profileId?: string; credentialId?: string; username?: string; instance?: string } {
  return { target: connection.target, profileId: connection.profileId, credentialId: connection.credentialId, username: connection.username, instance: connection.instance };
}

export function describeTarget(target: Target): string {
  if (target.kind === "local") return "This computer";
  if (target.kind === "wsl2") return `WSL2 · ${target.distribution}`;
  return `SSH · ${target.destination}`;
}
