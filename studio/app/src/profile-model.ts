/** Connection metadata only: no Orcan probe, DOM or secret persistence. */
import type { Connection, ConnectionProfile, Credential, Target } from "./types";

export const CHOOSE_SSH = "";
export const SYSTEM_SSH = "__system__";
export const INLINE_SSH = "__inline__";

export type ProfileValues = {
  id: string; name: string; location: string; distribution: string;
  host: string; user: string; choice: string;
};

export function buildProfile(values: ProfileValues, credentials: Credential[], editing?: ConnectionProfile): { profile: ConnectionProfile; connection: Connection } {
  const { id, name, location, distribution, host, user, choice } = values;
  if (location === "local") return { profile: { id, name, target: { kind: "local" } }, connection: { target: { kind: "local" }, label: name || "This computer" } };
  if (location === "wsl2") {
    if (!distribution) throw new Error("Choose a WSL2 distribution.");
    const target: Target = { kind: "wsl2", distribution };
    return { profile: { id, name, target }, connection: { target, label: name || `WSL2 ${distribution}` } };
  }
  if (location !== "ssh") throw new Error("Choose a connection type.");
  if (!host) throw new Error("Enter the server address.");
  if (/\s/.test(host) || /\s/.test(user)) throw new Error("The address and user cannot contain spaces.");
  if (choice === CHOOSE_SSH) throw new Error("Choose system SSH or a credential for this remote server.");
  const credential = credentials.find((item) => item.id === choice);
  const labelUser = choice === SYSTEM_SSH ? user : credential?.username;
  const label = name || `${labelUser ? `${labelUser}@` : ""}${host}`;
  if (choice === SYSTEM_SSH) {
    const target: Target = { kind: "ssh", destination: user ? `${user}@${host}` : host };
    return { profile: { id, name, target }, connection: { target, label } };
  }
  const target: Target = { kind: "ssh", destination: host };
  if (choice === INLINE_SSH && editing?.ssh) {
    return { profile: { id, name, target, ssh: { ...editing.ssh, username: user || undefined } }, connection: { target, label, profileId: editing.id } };
  }
  if (!credential) throw new Error("The selected credential no longer exists. Choose another sign-in method.");
  return { profile: { id, name, target, credential_id: choice }, connection: { target, label, credentialId: choice } };
}
