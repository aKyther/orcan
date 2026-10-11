import assert from "node:assert/strict";
import { test } from "node:test";
import { load, tick, compiledModule, setup, Element } from "./helpers.mjs";

test("background and interactive probes share only matching in-flight reads", async () => {
  const { probeRequests } = await load("probe-requests");
  const replies = new Map();
  let calls = 0;
  const probes = probeRequests(key => { calls++; return new Promise((resolve, reject) => replies.set(key, { resolve, reject })); });
  const first = probes.read("A");
  assert.equal(probes.read("A"), first);
  const second = probes.read("B");
  await tick();
  assert.equal(calls, 2);
  replies.get("A").resolve("report A");
  replies.get("B").reject(new Error("offline"));
  assert.equal(await first, "report A");
  await assert.rejects(second, /offline/);
  const retry = probes.read("B");
  await tick();
  assert.equal(calls, 3);
  replies.get("B").resolve("fresh B");
  assert.equal(await retry, "fresh B");
});

test("a later selection or disconnect expires both refresh and open activations", async () => {
  const { probeRequests } = await load("probe-requests");
  const probes = probeRequests(async () => "report");
  const refreshA = probes.begin();
  const openB = probes.begin();
  assert.equal(refreshA(), false);
  assert.equal(openB(), true);
  probes.invalidate();
  assert.equal(openB(), false);
});

test("activity uses the checked target instead of the previously active profile", async () => {
  setup();
  globalThis.localStorage = { getItem: () => null, setItem() {} };
  globalThis.Option = class extends Element { constructor(text, value) { super(); this.textContent = text; this.value = value; } };
  const { activityPanel } = await load("activity-panel", { "./activity": compiledModule("activity") });
  const container = new Element();
  container.before = () => {};
  const panel = activityPanel({ container, current: () => ({ label: "A", profileId: "a" }), profiles: () => [], open() {}, retry() {} });
  const job = panel.addJob("container check", "B", "B", "b");
  assert.equal(job.profileId, "b");
  assert.equal(job.enclave, "B");
  const unsaved = panel.addJob("container check", "Unsaved", "Unsaved");
  assert.equal(unsaved.profileId, undefined);
  panel.finishJob(job, "succeeded", "checked B");
  assert.equal(job.state, "succeeded");
  assert.equal(panel.addJob("sync", "active").profileId, "a");
});
