/** Browser preview only. Native operations never use this in-memory backend. */
import defaultIdentities from "./default-identities.json";
import { newId } from "./id";
import { normalizeProbeReport } from "./probe";
import { demoMode } from "./transport";
import { ownsEnclave, creationBlocker } from "./enclave-model";
import type { ConnectionProfile, Credential, MembershipArgs, ProbeReport, Target } from "./types";

const demoReport: ProbeReport = {
  sandbox: { version: "0.1.0-dev" },
  host: { os: "Linux", architecture: "x86_64" },
  capabilities: { docker: true, managed_projects: true, live_reconcile: true },
  runtime: {
    docker: { available: true, image: { name: "orcan:latest", present: true }, container: { name: "orcan-1", state: "running" }, agents: { codex: true, claude: true, gemini: true, copilot: false, cursor: true } },
    resources: { cpus: 4, memory: "8g", shm_size: "1g", tmpfs_size: "1g" },
    launch: { recorded: true, docker: false, git: true, network: null, ttyd: true, ttyd_auth: false },
  },
  paths: { home: "/home/orcan/.config/orcan", data: "/home/orcan/.config/orcan", projects_root: "/home/orcan/.config/orcan/sandbox", workspace_metadata_root: "/home/orcan/.config/orcan/workspaces", managed_worktrees_root: "/home/orcan/.config/orcan/worktrees" },
  context: {
    workspaces: [
      { name: "platform", projects: [{ name: "api", path: "/home/orcan/.config/orcan/sandbox/api", kind: "git_repository", branch: "main", dirty: false, repository_id: "api" }, { name: "web", path: "/home/orcan/.config/orcan/sandbox/web", kind: "git_repository", branch: "feature/studio", dirty: true, repository_id: "web" }] },
      { name: "mobile", projects: [{ name: "app", path: "/home/orcan/.config/orcan/sandbox/app", kind: "git_repository", branch: "main", dirty: false, repository_id: "app" }, { name: "api", path: "/home/orcan/.config/orcan/sandbox/api", kind: "git_repository", branch: "main", dirty: false, repository_id: "api" }] },
    ],
    managed_projects: ["api", "web", "app", "scratch"].map((name) => ({ path: `/home/orcan/.config/orcan/sandbox/${name}`, kind: "git_repository" })),
    repositories: [{ repository_id: "api", origin_url: "git@github.com:example/api.git", bindings: [{ workspace: "platform" }, { workspace: "mobile" }] }, { repository_id: "web", origin_url: "git@github.com:example/web.git", bindings: [{ workspace: "platform" }] }, { repository_id: "app", origin_url: "git@github.com:example/app.git", bindings: [{ workspace: "mobile" }] }],
    update_targets: [
      { name: "api", path: "/home/orcan/.config/orcan/sandbox/api", kind: "git_repository", role: "worktree_parent", worktree_count: 3, read_only: false, eligible: true, branch: "main", dirty: false, upstream: "origin/main", ahead: 0, behind: 2 },
      { name: "web", path: "/home/orcan/.config/orcan/sandbox/web", kind: "git_repository", role: "configured_mount", worktree_count: 0, read_only: true, eligible: false, branch: "feature/studio", dirty: true, upstream: "origin/feature/studio", ahead: 1, behind: 0 },
    ],
    configuration: { state: "synchronized", revision: "demo" },
  },
};

const demoStore: { profiles: ConnectionProfile[]; credentials: Credential[] } = {
  profiles: [
    { id: "demo", name: "Demo workstation", target: { kind: "local" } },
    { id: "gpu", name: "GPU box", target: { kind: "ssh", destination: "gpu.example" } },
    { id: "staging", name: "Staging VM", target: { kind: "ssh", destination: "staging.example" } },
  ],
  credentials: [],
};

function demoStoreCommand(command: string, args: Record<string, unknown>): unknown {
  const upsert = <T extends { id: string }>(items: T[], item: T) => [...items.filter((existing) => existing.id !== item.id), item];
  if (command === "list_profiles") return demoStore.profiles;
  if (command === "list_credentials") return demoStore.credentials;
  if (command === "save_profile") demoStore.profiles = upsert(demoStore.profiles, args.profile as ConnectionProfile);
  if (command === "create_credential") {
    const credential = args.credential as Credential;
    if (demoStore.credentials.some((item) => item.id === credential.id)) throw new Error("credential already exists; create a new credential instead");
    demoStore.credentials.push(credential);
  }
  if (command === "delete_profile") demoStore.profiles = demoStore.profiles.filter((item) => item.id !== args.id);
  if (command === "delete_credential") {
    const users = demoStore.profiles.filter((item) => item.credential_id === args.id).map((item) => item.name);
    if (users.length) throw new Error(`credential is used by: ${users.join(", ")}`);
    demoStore.credentials = demoStore.credentials.filter((item) => item.id !== args.id);
  }
  return null;
}

/** Read-only host report from `orcan-studio-preview snapshot`, served only by the dev server. */
export const previewSnapshot: Promise<ProbeReport | undefined> = demoMode
  ? fetch("/preview-probe.json", { cache: "no-store" }).then((response) => (response.ok ? response.json() : undefined)).catch(() => undefined)
  : Promise.resolve(undefined);

const demoReports = new Map<string, ProbeReport>();

/** Each demo container keeps its own report so membership changes stick until reload. */
async function demoReportFor(target: Target, instance?: string): Promise<ProbeReport> {
  const key = JSON.stringify(target) + (instance ? `:${instance}` : "");
  if (!demoReports.has(key)) {
    const snapshot = target.kind === "local" ? await previewSnapshot : undefined;
    const base = normalizeProbeReport(snapshot ?? (key.includes("gpu") ? { ...demoReport, runtime: { ...demoReport.runtime, docker: { ...demoReport.runtime.docker, container: { state: "exited" } } } } : demoReport));
    demoReports.set(key, structuredClone(base));
    if (instance) {
      const report = demoReports.get(key)!;
      report.paths.home += `/instances/${instance}`;
      report.paths.workspace_metadata_root = `${report.paths.home}/workspaces`;
      report.paths.managed_worktrees_root += `/instances/${instance}`;
      report.context.configuration = { state: "missing", source: "none", editable: false };
      report.context.workspaces = [];
      report.runtime.docker.container = { name: `orcan-${instance}`, state: "missing" };
    }
  }
  return demoReports.get(key)!;
}

/** Mirrors studio-settings.py: plan with blockers, then apply to the demo report. */
function demoMembership(report: ProbeReport, args: MembershipArgs): unknown {
  const workspace = report.context.workspaces.find((item) => item.name === args.workspace);
  const attached = workspace?.projects.some((project) => project.path === args.project) ?? false;
  const detach = args.action === "detach";
  const blockers = [detach && !workspace && "workspace does not exist", !detach && attached && "project is already attached", detach && workspace && !attached && "project is not attached to this workspace"].filter(Boolean);
  const plan = { creates_workspace: !workspace && !detach, changes: [...(!workspace && !detach ? [`create workspace ${args.workspace}`] : []), `${detach ? "detach" : "attach"} ${args.project} ${detach ? "from" : "to"} ${args.workspace}`, "run orcan sync"], blockers, ready: blockers.length === 0 };
  if (!args.apply) return { ok: true, plan };
  if (!plan.ready) throw new Error("apply requires a ready plan");
  if (detach) workspace!.projects = workspace!.projects.filter((project) => project.path !== args.project);
  else {
    const target = workspace ?? { name: args.workspace, projects: [] };
    if (!workspace) report.context.workspaces.push(target);
    target.projects.push({ name: args.project.split("/").pop(), path: args.project, kind: "git_repository", branch: "main", dirty: false });
  }
  return { ok: true, result: plan };
}

const demoIdentities = new Map(defaultIdentities.map((identity) => [identity.id, structuredClone(identity)]));
const demoIdentityVersions = new Map(defaultIdentities.map((identity) => [`${identity.id}:${identity.version}`, structuredClone(identity)]));
const demoGroups = new Map<string, import("./group-model").Group>();
const demoHostIds = new Map<string, string>();
export async function demoInvoke<T>(command: string, _args?: unknown): Promise<T> {
  await new Promise((resolve) => window.setTimeout(resolve, 180));
  if (command === "server_cleanup_inventory") return {
    cli: { path: "/home/demo/.local/bin/orcan", version: "orcan demo", removable: true, reason: "" },
    images: [{ image: "orcan:latest", id: "sha256:demo-cleanup", size: 2000000000, containers: ["orcan-1"] }, { image: "orcan:old", id: "sha256:demo-unused", size: 1800000000, containers: [] }], dockerError: null,
  } as T;
  if (command === "remove_server_cli") return "Demo CLI removed" as T;
  if (command === "list_groups") return structuredClone([...demoGroups.values()]) as T;
  if (command === "save_group") {
    const group = structuredClone((_args as { group: import("./group-model").Group }).group);
    if (!group.name.trim()) throw new Error("Name the enclave before saving");
    if ((demoGroups.get(group.id)?.revision ?? 0) !== group.revision) throw new Error("Enclave changed; reload before saving");
    group.revision++; demoGroups.set(group.id, group); return structuredClone(group) as T;
  }
  if (command === "list_identities") return { path: "Demo only — no files saved", identities: [...demoIdentities.values()] } as T;
  if (command === "save_identity") {
    const args = _args as { id?: string; expectedVersion?: number; name: string; description: string; instructions: string };
    const previous = args.id ? demoIdentities.get(args.id) : undefined;
    if (args.id && previous?.version !== args.expectedVersion) throw new Error("Identity changed; reload before editing");
    if (!args.name.trim() || !args.instructions.trim()) throw new Error("Name and instructions are required");
    const identity = { id: args.id ?? newId(), version: (previous?.version ?? 0) + 1, name: args.name.trim(), description: args.description, instructions: args.instructions };
    demoIdentities.set(identity.id, identity);
    demoIdentityVersions.set(`${identity.id}:${identity.version}`, identity);
    return identity as T;
  }
  if (command === "open_studio_data") return undefined as T;
  if (command === "current_user") return "developer" as T;
  if (command === "wsl_default_user") return "developer" as T;
  if (command === "test_connection") return "developer" as T;
  if (/profile|credential/.test(command)) return demoStoreCommand(command, (_args ?? {}) as Record<string, unknown>) as T;
  const enclave = (_args as { enclave?: { target: Target; instance?: string } } | undefined)?.enclave;
  if (command === "git_ssh_keys") return { keys: [{ name: "id_ed25519", algorithm: "ssh-ed25519", fingerprint: "Demo fingerprint — no real key" }] } as T;
  if (command === "transfer_git_ssh_key") {
    const args = (_args as { input: { destinationName: string; configure: boolean } }).input;
    return { name: args.destinationName, fingerprint: "Demo fingerprint — no real key copied", encrypted: false, configured: args.configure, config: `/demo/.ssh/orcan-git-${args.destinationName}.conf` } as T;
  }
  if (command === "test_git_ssh") return { ready: true, detail: "Demo only — no Git connection was made" } as T;
  if (command === "probe" && JSON.stringify(enclave?.target).includes("staging")) throw new Error("SSH connection failed: Connection timed out");
  if (["register_target", "group_probe", "group_start", "replace_container"].includes(command)) {
    if (JSON.stringify(enclave?.target).includes("staging")) throw new Error("Server offline");
    const report = await demoReportFor(enclave!.target, enclave!.instance);
    const args = _args as { hostId?: string; containerId?: string; apply?: boolean };
    if (command === "register_target") {
      if (["missing", "unavailable"].includes(report.runtime.docker.container.state)) throw new Error("Create or start the existing container before registering it");
      const key = JSON.stringify(enclave!.target);
      if (!demoHostIds.has(key)) demoHostIds.set(key, newId());
      report.target ??= { state: "ready", host_id: demoHostIds.get(key), container_id: newId() };
    } else {
      if (report.target?.state !== "ready" || report.target.host_id !== args.hostId || report.target.container_id !== args.containerId) throw new Error("Target identity mismatch. Refresh or register the replacement explicitly.");
      if (command === "group_start") {
        if (report.runtime.docker.container.state === "missing") throw new Error("Enclave Start never recreates missing containers");
        report.runtime.docker.container.state = "running";
      }
      if (command === "replace_container") {
        if (report.runtime.docker.container.state !== "missing") throw new Error("Remove the container with Down first");
        if (args.apply) { report.target = undefined; report.context.configuration = { state: "missing", source: "none", editable: false }; report.context.workspaces = []; }
        return { ok: true, result: { ready: true, archive: "/demo/retired/container", changes: ["archive instance configuration and workspace metadata", "preserve shared projects and data", "create replacement separately"] } } as T;
      }
    }
    return structuredClone(report) as T;
  }
  if (command === "list_instances") return { instances: [{ instance: null, container: "orcan-1", home: demoReport.paths.home }, ...[...demoReports.entries()].filter(([key, report]) => key.startsWith(`${JSON.stringify(enclave!.target)}:`) && ownsEnclave(report)).map(([key, report]) => ({ instance: key.slice(JSON.stringify(enclave!.target).length + 1), container: report.runtime.docker.container.name, home: report.paths.home }))] } as T;
  if (command === "server_capacity") return { cpus: 8, memoryBytes: 16 * 1024 ** 3, diskTotalBytes: 200 * 1024 ** 3, diskFreeBytes: 120 * 1024 ** 3, diskPath: (_args as { path?: string }).path } as T;
  if (command === "probe") return structuredClone(await demoReportFor(enclave!.target, enclave!.instance)) as T;
  if (command === "enclave_readiness") {
    const report = structuredClone(await demoReportFor(enclave!.target, enclave!.instance));
    report.capabilities.identity_templates = true;
    return { user: "developer", docker: { available: true, version: "demo", detail: "Docker ready" }, report, orcanError: null, images: report.runtime.docker.image ? [report.runtime.docker.image.name] : [], projectRoots: [report.paths.projects_root] } as T;
  }
  if (command === "enclave_action") {
    const report = await demoReportFor(enclave!.target, enclave!.instance);
    const args = _args as { apply: boolean; withGit: boolean; withDocker: boolean; withTtyd: boolean; ttydCredential?: string };
    const blocker = creationBlocker(report);
    if (blocker) throw new Error(blocker);
    const choice = _args as { identityId?: string; identityVersion?: number };
    const identity = choice.identityId ? demoIdentityVersions.get(`${choice.identityId}:${choice.identityVersion}`) : null;
    if (choice.identityId && !identity) throw new Error("Select an existing identity version");
    if (args.apply) {
      report.context.configuration = { state: "present", source: "config", editable: true };
      report.context.identity = identity ? structuredClone(identity) : null;
      const hostKey = JSON.stringify(enclave!.target);
      if (!demoHostIds.has(hostKey)) demoHostIds.set(hostKey, newId());
      report.target = { state: "ready", host_id: demoHostIds.get(hostKey), container_id: newId() };
      report.runtime.docker.container.state = "running";
      report.runtime.launch = { recorded: true, git: args.withGit, docker: args.withDocker, ttyd: args.withTtyd, ttyd_auth: Boolean(args.ttydCredential) };
      return { ok: true } as T;
    }
    return { plan: { ready: true, changes: ["create empty configuration", ...(identity ? [`identity: ${identity.name} v${identity.version} (immutable)`] : []), "run orcan sync", "start Orcan with selected access"] } } as T;
  }
  if (command === "runtime_action") {
    const report = await demoReportFor(enclave!.target, enclave!.instance);
    const action = (_args as { action: string }).action;
    report.runtime.docker.container.state = action === "down" ? "missing" : action === "stop" ? "exited" : "running";
    return null as T;
  }
  if (command === "membership_action") return demoMembership(await demoReportFor(enclave!.target, enclave!.instance), _args as MembershipArgs) as T;
  const root = demoReport.paths.projects_root;
  const worktrees = demoReport.paths.managed_worktrees_root;
  const responses: Record<string, unknown> = {
    parent_plan: { plan: { head: "abc1234", ready: true, blockers: [] } },
    import_plan: { plan: { destination: `${root}/new-repository`, destination_state: "absent", ready: true, blockers: [] } },
    import_apply: { result: { destination: `${root}/new-repository` } },
    worktree_plan: { plan: { destination: `${worktrees}/api/feature-context`, ready: true, blockers: [] } },
    worktree_apply: { result: { path: `${worktrees}/api/feature-context` } },
    worktree_cleanup: { plan: { ready: true, blockers: [] } },
    workspace_action: { plan: { ready: true, blockers: [], changes: ["update workspace", "run orcan sync"] } },
    runtime_action: null,
    ssh_host_key: { destination: "demo.example", algorithm: "ssh-ed25519", fingerprint: "SHA256:demo", status: "trusted" },
    trust_ssh_host_key: null,
    check_online_provision: { user: "developer", installedVersion: "orcan demo" },
    check_transfer: { installedVersion: "orcan demo", destinationUser: "developer", sourceImage: { image: "orcan:latest", id: "sha256:demo", size: "1024", architecture: "amd64" }, destinationImageId: "sha256:previous" },
    transfer_profiles: "Demo installation verified on destination.",
    remove_destination_image: "Demo image removed.",
    wsl_image_inventory_command: { image: "orcan:latest", id: "sha256:demo", size: "1024", architecture: "amd64" },
    check_image_destination: "amd64",
    verify_provision: "Demo destination verified.",
    check_docker: { available: true, version: "27.5.1", detail: "Docker daemon is ready" },
    provision_online: { version: "orcan demo" },
  };
  return (responses[command] ?? {}) as T;
}
