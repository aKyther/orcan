import assert from "node:assert/strict";
import { test } from "node:test";
import { load, dataModule } from "./helpers.mjs";

test("profile model builds transport-only profiles and rejects stale credentials", async () => {
  const { buildProfile, SYSTEM_SSH } = await load("profile-model");
  const values = { id: "id", name: "", location: "ssh", distribution: "", host: "server", user: "alice", choice: SYSTEM_SSH };
  assert.equal(buildProfile(values, []).profile.target.destination, "alice@server");
  const credential = { id: "key", name: "key", username: "bob", authentication: { kind: "password" } };
  const result = buildProfile({ ...values, choice: "key" }, [credential]);
  assert.equal(result.connection.label, "bob@server");
  assert.equal(result.profile.credential_id, "key");
  assert.equal(result.profile.target.destination, "server");
  assert.throws(() => buildProfile({ ...values, choice: "missing" }, []), /no longer exists/);
  assert.equal(buildProfile({ ...values, location: "wsl2", distribution: "Ubuntu" }, []).profile.target.distribution, "Ubuntu");
});

test("SSH trust coalesces concurrent requests and never saves a declined key", async () => {
  const { createSshTrust } = await load("ssh-trust");
  const commands = [];
  let approve = false;
  const trust = createSshTrust(async command => { commands.push(command); return { status: "unknown", destination: "server", fingerprint: "hash", algorithm: "ssh-ed25519" }; }, async () => approve);
  const first = trust("server", false);
  assert.equal(trust("server", false), first);
  assert.equal(await first, false);
  assert.deepEqual(commands, ["ssh_host_key"]);
  approve = true;
  assert.equal(await trust("server", false), true);
  assert.deepEqual(commands, ["ssh_host_key", "ssh_host_key", "trust_ssh_host_key"]);
});

test("trusted transport uses saved credentials for both transfer endpoints and fails closed", async () => {
  globalThis.window = { location: { search: "" } };
  const { createTrustedInvoker } = await load("transport", { "@tauri-apps/api/core": dataModule("export function invoke() {}") });
  const checks = [], calls = [];
  let approved = true;
  const invoke = createTrustedInvoker(async (...args) => { calls.push(args); return "ok"; }, () => [{ id: "remote", credential_id: "key" }], async (...args) => { checks.push(args); return approved; });
  const endpoint = { target: { kind: "ssh", destination: "server" }, profileId: "remote" };
  assert.equal(await invoke("transfer", { input: { source: endpoint, destination: endpoint } }), "ok");
  assert.deepEqual(checks, [["server", false]]);
  approved = false;
  await assert.rejects(invoke("probe", { enclave: endpoint }), /No connection was made/);
  assert.equal(calls.length, 1);
});

test("unknown Git status is visible in project alerts", async () => {
  const { projectAlerts } = await load("context-model");
  assert.deepEqual(projectAlerts({ context: { update_targets: [] } }, { path: "/app", dirty: null }), ["Git status unknown"]);
});

test("parent index preserves preference and is rebuilt for changed reports", async () => {
  const { indexParents } = await load("context-model");
  const target = (path, role, name) => ({ path, role, name, repository_id: "repo", eligible: true, read_only: true, worktree_count: 1 });
  const report = { context: { update_targets: [target("/mount", "configured_mount", "mount"), target("/source", "worktree_parent", "source")] } };
  const first = indexParents(report, []);
  assert.equal(first.forProject({ path: "/mount", repository_id: "repo" }).path, "/source");
  report.context.update_targets = [target("/replacement", "worktree_parent", "new")];
  assert.equal(indexParents(report, []).forProject({ path: "/tree", repository_id: "repo" }).path, "/replacement");
  assert.equal(first.forProject({ path: "/tree", repository_id: "repo" }).path, "/source");
});

test("map geometry coalesces resize and group-toggle requests into one frame", async () => {
  const { createMapConnections } = await load("map-connections");
  const frames = [];
  globalThis.requestAnimationFrame = callback => (frames.push(callback), frames.length);
  const canvas = new EventTarget();
  canvas.querySelectorAll = () => [];
  canvas.getBoundingClientRect = () => ({ width: 800, height: 300 });
  const container = { querySelectorAll: () => [] };
  let draws = 0;
  const layer = () => ({ setAttribute() {}, replaceChildren() { draws++; } });
  globalThis.window = { matchMedia: () => ({ matches: true }) };
  try {
    const connections = createMapConnections(canvas, container, container, layer(), layer(), () => ({}));
    connections.schedule();
    connections.schedule();
    canvas.dispatchEvent(new Event("toggle"));
    assert.equal(frames.length, 1);
    frames.shift()();
    assert.equal(draws, 2);
    connections.highlight();
    assert.equal(draws, 2);
    connections.schedule();
    assert.equal(frames.length, 1);
  } finally {
    delete globalThis.requestAnimationFrame;
  }
});

test("demo backend preserves per-container state without mutating another container", async () => {
  globalThis.window = { setTimeout: resolve => { resolve(); return 0; } };
  const { demoInvoke } = await load("demo", {
    "./default-identities.json": dataModule("export default []"),
    "./transport": dataModule("export const demoMode = false"),
    "./probe": dataModule("export function normalizeProbeReport(value) { return value; }"),
    "./enclave-model": dataModule("export function ownsEnclave() { return false; } export function creationBlocker() {}"),
  });
  const first = { target: { kind: "local" }, instance: "first" };
  const second = { target: { kind: "local" }, instance: "second" };
  await demoInvoke("membership_action", { enclave: first, workspace: "review", project: "/app", action: "attach", apply: true });
  const report = await demoInvoke("probe", { enclave: first });
  assert.equal(report.context.workspaces[0].name, "review");
  assert.deepEqual((await demoInvoke("probe", { enclave: second })).context.workspaces, []);
  report.context.workspaces.length = 0;
  assert.equal((await demoInvoke("probe", { enclave: first })).context.workspaces.length, 1);
});
