import type { ProbeReport } from "./types";

export type LifecycleAction = "start" | "stop" | "restart" | "down";

/** Configuration and an existing container both reserve this instance name. */
export function ownsEnclave(report?: ProbeReport): boolean {
  if (!report) return false;
  const config = report.context.configuration;
  return config.source === "config" || ["present", "synchronized", "runtime_index"].includes(config.state)
    || !["missing", "unavailable", ""].includes(report.runtime.docker.container.state);
}

export function creationBlocker(report?: ProbeReport): string | undefined {
  if (!report) return "Check the destination first. Orcan CLI must be installed and support Studio.";
  if (ownsEnclave(report)) return "This container name already has a configuration or container. Choose another name or open it.";
  if (!report.capabilities.docker) return "Docker is not ready for this user.";
  if (!report.runtime.docker.image) return "Orcan did not report its required image. Update the CLI and check again.";
  if (!report.runtime.docker.image.present) return `Transfer ${report.runtime.docker.image.name} to this profile first.`;
  return undefined;
}

export function lifecycleBlocker(report: ProbeReport, action: LifecycleAction): string | undefined {
  const declared = report.control?.operations?.runtime_lifecycle;
  if (declared && !declared.available) return declared.reason || "Orcan has disabled container controls.";
  if (!report.capabilities.docker) return "Docker is not available.";
  const state = report.runtime.docker.container.state;
  if (action === "down") return ["missing", "unavailable"].includes(state) ? "There is no container to remove." : undefined;
  if (action !== "start") return state === "running" ? undefined : "The container is not running.";
  if (state === "running") return "The container is already running.";
  if (!["missing", "unavailable"].includes(state)) return ["created", "exited"].includes(state) ? undefined : "The container is not in a stopped state. Refresh its status.";
  if (!report.runtime.launch?.recorded) return "No container or saved launch options. Set up this container first.";
  if (report.runtime.launch.ttyd_auth) return "The container was removed. Re-enter browser-terminal credentials on the host before recreating it.";
  if (!report.runtime.docker.image?.present) return "The required image is not available. Transfer it first.";
  return undefined;
}
