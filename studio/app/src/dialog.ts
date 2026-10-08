import { el } from "./dom";

type DialogOptions = { title?: string; confirmLabel?: string; danger?: boolean };
let queue: Promise<unknown> = Promise.resolve();

function request(message: string, options: DialogOptions, input?: { label: string; value: string }): Promise<string | null> {
  const task = queue.catch(() => undefined).then(() => new Promise<string | null>((resolve) => {
    const previousFocus = document.activeElement as HTMLElement | null;
    const dialog = el("dialog", { className: "plan-dialog studio-dialog" });
    const heading = el("h2", { id: "studio-dialog-title", textContent: options.title ?? "Confirm action" });
    const body = el("p", { id: "studio-dialog-message", className: "dialog-message", textContent: message });
    dialog.setAttribute("aria-labelledby", heading.id);
    dialog.setAttribute("aria-describedby", body.id);
    const cancel = el("button", { type: "button", className: "secondary", textContent: "Cancel", autofocus: !input });
    const confirm = el("button", { type: "submit", className: options.danger ? "dialog-danger" : "", textContent: options.confirmLabel ?? "Confirm" });
    const form = el("form", {}, heading, body);
    const field = input ? el("input", { type: "text", value: input.value, required: true, autofocus: true }) : undefined;
    if (field && input) form.append(el("label", {}, input.label, field));
    form.append(el("div", { className: "form-actions dialog-actions" }, cancel, confirm));
    cancel.addEventListener("click", () => dialog.close("cancel"));
    form.addEventListener("submit", (event) => { event.preventDefault(); dialog.close("confirm"); });
    dialog.addEventListener("close", () => {
      const answer = dialog.returnValue === "confirm" ? field?.value.trim() ?? "" : null;
      dialog.remove();
      previousFocus?.focus();
      resolve(answer);
    }, { once: true });
    dialog.append(form);
    document.body.append(dialog);
    dialog.showModal();
    if (field) { field.focus(); field.select(); } else cancel.focus();
  }));
  queue = task;
  return task;
}

export async function confirmAction(message: string, options: DialogOptions = {}): Promise<boolean> {
  return (await request(message, options)) !== null;
}

export function promptText(message: string, value: string, options: DialogOptions = {}): Promise<string | null> {
  return request(message, options, { label: "New name", value });
}
