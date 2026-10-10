import { actionButton, el } from "./dom";
import { validateBranches } from "./context-model";
import { enclaveInput, type invokeTauri } from "./transport";
import type { Connection } from "./types";

type Options = {
  source: HTMLSelectElement; branch: HTMLInputElement; state: HTMLElement;
  existing: HTMLElement; output: HTMLElement;
  connection: () => Connection | undefined; root: () => string | null;
  invoke: typeof invokeTauri; invalidate: () => void; changed: () => void;
};

/** Owns branch discovery and selection, including late-response protection. */
export function branchPicker(options: Options) {
  let branches: string[] = [];
  let sequence = 0;
  let known = false;
  let loading = false;
  const browser = el("details", { className: "branch-browser" });
  const summary = el("summary");
  const search = el("input", { placeholder: "filter branches" });
  const list = el("div", { className: "branch-list" });
  browser.append(summary, search, list);
  browser.hidden = true;
  options.existing.after(browser);

  function render() {
    const name = options.branch.value.trim();
    const exists = branches.includes(name);
    options.state.textContent = !name ? "Enter a branch name." : loading ? "Checking branch names…" : !known
      ? "Branch list unavailable. Preview the plan to verify this name."
      : exists ? "Existing branch · this worktree will check it out." : "New branch · Orcan will create it for this worktree.";
    options.state.classList.toggle("existing", known && exists);
    summary.textContent = `Local branches (${branches.length})`;
    browser.hidden = branches.length === 0;
    const query = search.value.trim().toLowerCase();
    list.replaceChildren(...branches.filter(name => name.toLowerCase().includes(query)).slice(0, 40).map(name => actionButton(name, () => {
      options.branch.value = name;
      options.invalidate();
      render();
    })));
  }

  async function refresh() {
    const request = ++sequence;
    const connection = options.connection(), repo = options.source.value;
    branches = [];
    known = false;
    loading = Boolean(connection && repo);
    render();
    options.changed();
    if (!connection || !repo) return;
    options.existing.textContent = "Reading local branches from the Git source…";
    const latest = () => request === sequence && options.connection() === connection && options.source.value === repo;
    try {
      const response = await options.invoke<{ branches: unknown }>("worktree_branches", { enclave: enclaveInput(connection), repo, worktreesRoot: options.root() });
      if (!latest()) return;
      branches = validateBranches(response.branches);
      known = true;
    } catch (error) {
      if (!latest()) return;
      options.output.textContent = `Could not read branches: ${String(error)}`;
    }
    loading = false;
    render();
    options.changed();
  }

  options.source.addEventListener("change", () => { options.invalidate(); void refresh(); });
  options.branch.addEventListener("input", () => {
    options.invalidate();
    if (known && branches.includes(options.branch.value.trim())) options.output.textContent = `Existing branch: ${options.branch.value.trim()}. Preview the plan before checking it out.`;
    render();
  });
  search.addEventListener("input", render);
  return { refresh, branches: () => branches };
}
