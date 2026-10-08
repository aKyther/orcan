import { listen } from "@tauri-apps/api/event";
import { el } from "./dom";
import { demoMode } from "./transport";

type ProgressEvent = { operationId: string; stage: string; bytes: number; total?: number | null };
const labels: Record<string, string> = {
  preparing: "Preparing connection",
  checking: "Checking requirements",
  exporting: "Exporting to Studio",
  transferring: "Sending to destination",
  installing: "Installing on destination",
  verifying: "Verifying installation",
  completed: "Completed",
  failed: "Failed",
};

function bytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KiB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MiB`;
  return `${(value / 1024 ** 3).toFixed(2)} GiB`;
}

function duration(seconds: number): string {
  return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
}

export function isProvisionRunning(output: HTMLElement): boolean {
  return output.getAttribute("aria-busy") === "true";
}

/** Subscribe before invoking; dispose on success/error and scope concurrent jobs. */
export async function withProvisionProgress<T>(output: HTMLElement, title: string, operation: (operationId: string) => Promise<T>): Promise<T> {
  if (isProvisionRunning(output)) throw new Error("A transfer is already running. Wait for its result.");
  const operationId = crypto.randomUUID();
  const started = Date.now();
  let phaseStarted = started;
  let update: ProgressEvent = { operationId, stage: "preparing", bytes: 0 };
  const heading = el("strong");
  const percentage = el("span", { className: "transfer-percentage" });
  percentage.setAttribute("aria-live", "off");
  const header = el("div", { className: "transfer-progress-header" }, heading, percentage);
  const detail = el("span", { className: "transfer-detail" });
  detail.setAttribute("aria-live", "off");
  const bar = document.createElement("progress");
  bar.max = 100;
  bar.setAttribute("aria-label", "Transfer phase progress");
  const card = el("div", { className: "transfer-progress", role: "status" }, header, bar, detail);
  const global = el("div", { className: "transfer-status-item" });
  global.title = "Transfer is running. Keep Studio open; view details in Provisioning.";
  const status = document.querySelector<HTMLElement>("#transfer-status")!;
  status.append(global);
  status.hidden = false;
  output.replaceChildren(card);
  output.setAttribute("aria-busy", "true");
  const controls = [...(output.closest(".panel")?.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLButtonElement>("input,select,button") ?? [])].map((control) => ({ control, disabled: control.disabled }));
  for (const { control } of controls) control.disabled = true;
  const render = () => {
    const stage = labels[update.stage] ?? update.stage;
    const elapsed = Math.floor((Date.now() - started) / 1000);
    const phaseSeconds = (Date.now() - phaseStarted) / 1000;
    const percent = update.total && update.total > 0 ? Math.min(100, Math.floor(100 * update.bytes / update.total)) : undefined;
    const remaining = update.total ? Math.max(0, update.total - update.bytes) : undefined;
    const speed = phaseSeconds >= 2 && update.bytes > 0 ? update.bytes / phaseSeconds : undefined;
    const eta = remaining !== undefined && remaining > 0 && speed ? Math.ceil(remaining / speed) : undefined;
    if (percent === undefined) bar.removeAttribute("value"); else bar.value = percent;
    percentage.textContent = percent === undefined ? duration(elapsed) : `${percent}%`;
    if (heading.textContent !== stage) heading.textContent = stage;
    detail.textContent = `${update.bytes ? `${bytes(update.bytes)}${update.total ? ` / ${bytes(update.total)}` : ""} · ` : ""}${remaining !== undefined ? `${bytes(remaining)} left · ` : ""}${speed ? `${bytes(speed)}/s · ` : ""}${eta !== undefined ? `~${duration(eta)} left · ` : ""}${duration(elapsed)} elapsed`;
    card.title = update.stage === "exporting" ? "Total size and remaining time are known after export. Source preparation may take a while." : update.stage === "installing" ? "Data sent. Waiting for destination installation to finish." : update.stage === "preparing" ? "Waiting for connection or server identity approval." : "Remaining time is an estimate for this transfer phase, excluding installation and verification.";
    global.textContent = `${title} · ${stage}${percent !== undefined ? ` · ${percent}%` : ""}${remaining !== undefined ? ` · ${bytes(remaining)} left` : ""}${eta !== undefined ? ` · ~${duration(eta)}` : ""} · ${duration(elapsed)}`;
  };
  render();
  const timer = window.setInterval(render, 1000);
  let unlisten: (() => void) | undefined;
  try {
    if (!demoMode) {
      unlisten = await listen<ProgressEvent>("provision-progress", (event) => {
        if (event.payload.operationId !== operationId) return;
        if (event.payload.stage !== update.stage) phaseStarted = Date.now();
        update = event.payload;
        render();
      });
    }
    return await operation(operationId);
  } finally {
    window.clearInterval(timer);
    unlisten?.();
    global.remove();
    status.hidden = status.childElementCount === 0;
    output.removeAttribute("aria-busy");
    for (const { control, disabled } of controls) control.disabled = disabled;
  }
}
