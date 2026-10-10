import { readFileSync } from "node:fs";
import ts from "typescript";

export class Element extends EventTarget {
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

export const tick = () => new Promise((resolve) => setImmediate(resolve));

export const dataModule = (source) => `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;

export function setup() {
  const status = new Element();
  globalThis.document = { body: new Element(), activeElement: new Element(), createElement: () => new Element(), querySelector: () => status };
  globalThis.window = { setInterval, clearInterval };
  return status;
}

export async function load(name, imports = {}) {
  const dom = dataModule(transpile("dom"));
  let source = transpile(name);
  for (const [path, module] of Object.entries({ "./identity-instructions": dataModule(transpile("identity-instructions")), "./dom": dom, "./id": dataModule(transpile("id")), ...imports })) source = source.replace(JSON.stringify(path), JSON.stringify(module));
  return import(dataModule(`${source}\n// isolated test ${Math.random()}`));
}


const compiled = new Map();
function transpile(name) {
  if (!compiled.has(name)) compiled.set(name, ts.transpileModule(readFileSync(new URL(`../src/${name}.ts`, import.meta.url), "utf8"), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText);
  return compiled.get(name);
}
