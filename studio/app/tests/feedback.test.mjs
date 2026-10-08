// Lightweight behavior tests: no browser emulator or new runtime dependency.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import ts from "typescript";

class Element extends EventTarget {
  children = [];
  attributes = new Map();
  disabled = false;
  hidden = false;
  textContent = "";
  append(...children) { this.children.push(...children); for (const child of children) if (typeof child === "object" && child !== null) child.parent = this; }
  replaceChildren(...children) { this.children = []; this.append(...children); }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter((child) => child !== this); }
  setAttribute(name, value) { this.attributes.set(name, value); }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  removeAttribute(name) { this.attributes.delete(name); }
  get childElementCount() { return this.children.length; }
  closest() { return this.panel; }
  querySelectorAll() { return this.controls ?? []; }
  focus() { document.activeElement = this; }
  select() { this.selected = true; }
  showModal() { this.open = true; }
  close(value = "") { this.returnValue = value; this.open = false; this.dispatchEvent(new Event("close")); }
}

const tick = () => new Promise((resolve) => setImmediate(resolve));
const dataModule = (source) => `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;

function setup() {
  const status = new Element();
  globalThis.document = { body: new Element(), activeElement: new Element(), createElement: () => new Element(), querySelector: () => status };
  globalThis.window = { setInterval, clearInterval };
  return status;
}

async function load(name, imports = {}) {
  const transpile = (source) => ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
  const dom = dataModule(transpile(readFileSync(new URL("../src/dom.ts", import.meta.url), "utf8")));
  let source = transpile(readFileSync(new URL(`../src/${name}.ts`, import.meta.url), "utf8"));
  for (const [path, module] of Object.entries({ "./dom": dom, ...imports })) source = source.replace(JSON.stringify(path), JSON.stringify(module));
  return import(dataModule(`${source}\n// isolated test ${Math.random()}`));
}

test("container cards distinguish fresh, pending, stale and unchecked states", async () => {
  const { containerStateLabel } = await load("server-model");
  const report = { runtime: { docker: { container: { state: "running" } } } };
  assert.equal(containerStateLabel(), "not checked");
  assert.equal(containerStateLabel({ state: "offline" }), "not checked");
  assert.equal(containerStateLabel({ state: "offline", report }), "stale");
  assert.equal(containerStateLabel({ state: "checking", report }), "checking…");
  assert.equal(containerStateLabel({ state: "online", report }), "running");
  assert.equal(containerStateLabel({ state: "online" }), "unknown");
});

test("container selections persist by profile and reject malformed storage", async () => {
  let stored = '{"a":"tester","b":"","bad":"../../escape","number":3}';
  globalThis.localStorage = { getItem: () => stored, setItem: (_key, value) => { stored = value; } };
  const { loadContainerSelections, persistContainerSelections } = await load("server-model");
  const selections = loadContainerSelections();
  assert.deepEqual([...selections], [["a", "tester"], ["b", ""]]);
  selections.set("a", "developer");
  persistContainerSelections(selections);
  assert.equal(loadContainerSelections().get("a"), "developer");
  stored = "invalid JSON";
  assert.equal(loadContainerSelections().size, 0);
  globalThis.localStorage.getItem = () => { throw new Error("unavailable"); };
  assert.equal(loadContainerSelections().size, 0);
});

test("confirmation is centered, defaults to Cancel, restores focus, and queues dialogs", async () => {
  setup();
  const previous = document.activeElement;
  const { confirmAction } = await load("dialog");
  const first = confirmAction("Remove image?", { title: "Remove", danger: true });
  const second = confirmAction("Continue?");
  await tick();
  assert.equal(document.body.children.length, 1);
  let dialog = document.body.children[0];
  assert.equal(dialog.open, true);
  assert.equal(document.activeElement.textContent, "Cancel");
  dialog.close(); // Native dialog Escape/cancel path.
  assert.equal(await first, false);
  await tick();
  dialog = document.body.children[0];
  dialog.children[0].dispatchEvent(new Event("submit", { cancelable: true }));
  assert.equal(await second, true);
  assert.equal(document.body.children.length, 0);
  assert.equal(document.activeElement, previous);
});

test("workspace name uses an inline selected field, not a browser prompt", async () => {
  setup();
  const { promptText } = await load("dialog");
  const pending = promptText("Rename workspace", "original");
  await tick();
  const dialog = document.body.children[0];
  const field = dialog.children[0].children[2].children[1];
  assert.equal(field.selected, true);
  field.value = "  updated  ";
  dialog.children[0].dispatchEvent(new Event("submit", { cancelable: true }));
  assert.equal(await pending, "updated");
});

function enclaveFixture(state = "missing") {
  return {
    capabilities: { docker: true },
    runtime: { docker: { image: { name: "orcan:latest", present: true }, container: { name: "orcan-1", state } }, launch: { recorded: true, ttyd_auth: false } },
    context: { configuration: { state: "missing", source: "none" } },
  };
}

test("enclave setup distinguishes missing CLI, Docker, image and existing ownership", async () => {
  const { ownsEnclave, creationBlocker } = await load("enclave-model");
  assert.match(creationBlocker(), /CLI/);
  const report = enclaveFixture();
  assert.equal(creationBlocker(report), undefined);
  assert.equal(ownsEnclave(report), false);
  report.runtime.docker.image.present = false;
  assert.match(creationBlocker(report), /Transfer orcan:latest/);
  delete report.runtime.docker.image;
  assert.match(creationBlocker(report), /Update/);
  report.capabilities.docker = false;
  assert.match(creationBlocker(report), /Docker/);
  report.context.configuration = { state: "present", source: "config" };
  assert.equal(ownsEnclave(report), true);
  assert.match(creationBlocker(report), /container name already/);
  assert.equal(ownsEnclave(enclaveFixture("exited")), true);
});

test("existing protected containers can restart and start without recreating", async () => {
  const { lifecycleBlocker } = await load("enclave-model");
  const report = enclaveFixture("running");
  report.runtime.launch.ttyd_auth = true;
  assert.equal(lifecycleBlocker(report, "restart"), undefined);
  assert.equal(lifecycleBlocker(report, "stop"), undefined);
  assert.match(lifecycleBlocker(report, "start"), /already running/);
  report.runtime.docker.container.state = "exited";
  assert.equal(lifecycleBlocker(report, "start"), undefined);
  assert.equal(lifecycleBlocker(report, "down"), undefined);
  report.runtime.docker.container.state = "missing";
  assert.match(lifecycleBlocker(report, "down"), /no container/);
  assert.match(lifecycleBlocker(report, "start"), /credentials/);
  report.runtime.launch.ttyd_auth = false;
  assert.equal(lifecycleBlocker(report, "start"), undefined);
  report.control = { operations: { runtime_lifecycle: { available: false, reason: "Host denied" } } };
  assert.equal(lifecycleBlocker(report, "start"), "Host denied");
});

test("progress is scoped, counts remaining bytes, blocks re-entry, and disposes on error", async () => {
  const status = setup();
  const listeners = [];
  globalThis.__progressListeners = listeners;
  const { withProvisionProgress, isProvisionRunning } = await load("provision-progress", {
    "./transport": dataModule("export const demoMode = false;"),
    "@tauri-apps/api/event": dataModule("export async function listen(_, callback) { globalThis.__progressListeners.push(callback); return () => globalThis.__progressListeners.splice(0); }"),
  });
  const output = new Element();
  const control = new Element();
  output.panel = new Element();
  output.panel.controls = [control];
  let reject;
  let id;
  const pending = withProvisionProgress(output, "A → B", (operationId) => { id = operationId; return new Promise((_, fail) => { reject = fail; }); });
  await tick();
  assert.equal(isProvisionRunning(output), true);
  assert.equal(control.disabled, true);
  await assert.rejects(withProvisionProgress(output, "second", () => Promise.resolve()), /already running/);
  listeners[0]({ payload: { operationId: id, stage: "transferring", bytes: 1024, total: 4096 } });
  const [header, bar, detail] = output.children[0].children;
  const [heading, percentage] = header.children;
  assert.equal(bar.value, 25);
  assert.equal(percentage.textContent, "25%");
  assert.match(detail.textContent, /3.0 KiB left/);
  listeners[0]({ payload: { operationId: "other-job", stage: "failed", bytes: 0 } });
  assert.equal(heading.textContent, "Sending to destination");
  listeners[0]({ payload: { operationId: id, stage: "installing", bytes: 0 } });
  assert.equal(bar.getAttribute("value"), null);
  assert.match(output.children[0].title, /Data sent/);
  assert.doesNotMatch(percentage.textContent, /%/);
  reject(new Error("connection lost"));
  await assert.rejects(pending, /connection lost/);
  assert.equal(isProvisionRunning(output), false);
  assert.equal(control.disabled, false);
  assert.equal(status.hidden, true);
  assert.equal(listeners.length, 0);
});
