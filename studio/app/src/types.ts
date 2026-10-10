export type Target =
  | { kind: "local" }
  | { kind: "wsl2"; distribution: string }
  | { kind: "ssh"; destination: string };

export type ProbeReport = {
  target?: { state: string; host_id?: string; container_id?: string; reason?: string };
  sandbox: { version: string };
  host: { os: string; architecture: string; user?: string };
  capabilities: { docker: boolean; managed_projects: boolean; live_reconcile: boolean; identity_templates?: boolean };
  runtime: {
    docker: { available?: boolean; image?: { name: string; present: boolean }; container: { name?: string; state: string }; agents?: Record<string, boolean> };
    resources?: { cpus?: string | number; memory?: string; shm_size?: string; tmpfs_size?: string };
    defaults?: { resources?: { cpus?: number; memory?: string }; ttyd?: { host_port?: number } };
    launch?: { recorded: boolean; docker?: boolean; git?: boolean; github?: string | null; gitlab?: string | null; network?: string | null; ttyd?: boolean; ttyd_auth?: boolean };
  };
  paths: { home: string; data: string; cache?: string; projects_root: string; workspace_metadata_root: string; managed_worktrees_root: string };
  control?: {
    operations?: Record<string, { available: boolean; reason?: string }>;
    settings?: Array<{ id: string; label: string; state: "editable" | "locked"; value: string; detail: string; action?: "contexts" | "runtime" }>;
  };
  context: {
    identity?: Identity | null;
    workspaces: Array<{
      name: string;
      projects: Array<{ name?: string; path: string; kind: string; writable?: boolean; branch?: string; dirty?: boolean | null; upstream?: string; ahead?: number; behind?: number; repository_id?: string }>;
    }>;
    managed_projects: Array<{ path: string; kind: string; writable?: boolean; repository_id?: string; branch?: string; dirty?: boolean | null; upstream?: string; ahead?: number; behind?: number; origin_url?: string }>;
    repositories: Array<{ repository_id: string; origin_url?: string; bindings: Array<{ workspace: string }> }>;
    update_targets: Array<{ name: string; path: string; kind: string; role: "worktree_parent" | "configured_mount"; worktree_count: number; read_only: boolean; eligible: boolean; repository_id?: string; branch?: string; dirty?: boolean | null; upstream?: string; ahead?: number; behind?: number }>;
    configuration: { state: string; revision?: string; source?: "config" | "runtime_index" | "none"; editable?: boolean; path?: string };
  };
};

export type SshAuthentication =
  | { kind: "agent" }
  | { kind: "password" }
  | { kind: "private_key"; path: string; has_passphrase: boolean };
export type SshOptions = { username?: string; authentication: SshAuthentication };
export type ConnectionProfile = { id: string; name: string; target: Target; ssh?: SshOptions; credential_id?: string };
export type Credential = { id: string; name: string; username: string; authentication: SshAuthentication };
export type Connection = { target: Target; label: string; profileId?: string; credentialId?: string; username?: string; instance?: string };
export type SshHostKeyOffer = { destination: string; algorithm: string; fingerprint: string; status: "trusted" | "unknown" | "changed" };
export type MembershipArgs = { action: "attach" | "detach"; workspace: string; project: string; apply: boolean };
export type ProjectRef = { name: string; path: string; kind?: string };

export type Identity = { id: string; version: number; name: string; description: string; instructions: string };
