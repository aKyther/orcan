import { newId } from "./id";
import type { invokeTauri } from "./transport";

/** Only read-only probes expose Cancel. Mutations require refreshed state,
 * not a misleading UI promise that remote work has been undone. */
export function createCheckInvoker(invoke: typeof invokeTauri, container: HTMLElement) {
  return async <T>(command: string, input?: unknown): Promise<T> => {
    const args = input as { enclave?: Record<string, unknown> } | undefined;
    if (command !== "probe" || !args?.enclave) return invoke<T>(command, input);
    const operationId = newId();
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary";
    button.textContent = "Cancel check";
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const cancelled = await invoke<boolean>("cancel_operation", { operationId });
        button.textContent = cancelled ? "Cancelling…" : "Check is finishing…";
      } catch {
        button.textContent = "Could not cancel";
        button.disabled = false;
      }
    });
    container.append(button);
    try {
      return await invoke<T>(command, { ...args, enclave: { ...args.enclave, operationId } });
    } finally { button.remove(); }
  };
}
