import { invoke as tauriInvoke } from "@tauri-apps/api/core";
import type { Connection, Target } from "./types";

export const demoMode = new URLSearchParams(window.location.search).has("demo") || !("__TAURI_INTERNALS__" in window);

export function invokeTauri<T>(command: string, args?: unknown): Promise<T> {
  return tauriInvoke<T>(command, args as never);
}

/** The minimal connection descriptor accepted by the native Studio commands. */
export function enclaveInput(connection: Connection): { target: Target; profileId?: string; credentialId?: string; username?: string } {
  return { target: connection.target, profileId: connection.profileId, credentialId: connection.credentialId, username: connection.username };
}

export function describeTarget(target: Target): string {
  if (target.kind === "local") return "This computer";
  if (target.kind === "wsl2") return `WSL2 · ${target.distribution}`;
  return `SSH · ${target.destination}`;
}

export function cacheKey(target: Target): string {
  return `orcan-studio:snapshot:${JSON.stringify(target)}`;
}
