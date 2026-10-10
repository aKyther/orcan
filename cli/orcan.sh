#!/usr/bin/env bash
# orcan CLI entry — dispatch to cli/commands/<name>.sh
set -Eeuo pipefail

ORCAN_CLI_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCAN_ROOT="$(cd -- "${ORCAN_CLI_DIR}/.." && pwd)"
export ORCAN_ROOT

# Select a named runtime before bootstrap resolves any paths or Compose files.
if [[ "${1:-}" == "--instance" ]]; then
    instance="${2:-}"
    if [[ ! "$instance" =~ ^[a-z][a-z0-9-]{0,47}$ ]]; then
        printf 'invalid instance name: use 1-48 lowercase letters, digits or hyphens, starting with a letter\n' >&2
        exit 2
    fi
    base_home="${ORCAN_INSTANCES_ROOT:-${XDG_CONFIG_HOME:-${HOME}/.config}/orcan}"
    if [[ -L "${base_home}/instances" || -L "${base_home}/instances/${instance}" ]]; then
        printf 'refusing a symlinked instance configuration directory\n' >&2
        exit 2
    fi
    export ORCAN_HOME="${base_home}/instances/${instance}"
    export ORCAN_DATA="${ORCAN_DATA:-${base_home}}"
    export ORCAN_INSTANCE="${instance}"
    export ORCAN_NAMED_INSTANCE="${instance}"
    export COMPOSE_PROJECT_NAME="orcan-${instance}"
    export ORCAN_CONFIG_FILE="${ORCAN_HOME}/orcan.config.json"
    export ORCAN_ENV_FILE="${ORCAN_HOME}/.env"
    export ORCAN_RUNTIME_DIR="${ORCAN_HOME}/mounts"
    shift 2
fi

# shellcheck source=lib/common.sh
source "${ORCAN_CLI_DIR}/lib/common.sh"

usage() {
    cat <<'EOF'
orcan — work-context orchestrator for coding agents

Usage:
  orcan <command> [arguments]
  orcan --instance NAME <command> [arguments]

Commands:
  init         No PATH: TUI to create/edit workspaces + sync + show
               (--cli: old sequential prompt wizard instead)
               PATH: non-interactive scaffold (scripts/CI) + sync + show
  sync         Apply orcan.config.json → .env + mounts/* for Compose
  migrate      Move projects under the managed root (fewer future recreates)
  context      Manage context (show | add | tui | worktrees | worktree | assert | hook)
  settings     Edit tool settings (tmux, ttyd) — separate from workspaces
  up           Start container (orcan enter; --web-terminal | --web-terminal-auth for browser)
  down         Stop containers
  build        Build an explicit --agent selection as orcan:latest + orcan:<VERSION>
  pull         Pull portable all-agents orcan:<VERSION> → orcan:latest
  publish      Manual push of all-agents orcan:latest (not part of build)
  url          Print browser terminal URL
  logs         Follow container logs
  enter        Local terminal into the container (alias: go-in)
  attach       Create or resume one workspace tmux session
  update       Dev channel: fast-forward to origin/main
  upgrade      Release channel: checkout newest release tag (or --to VERSION)
  downgrade    Previous release (or --to VERSION)
  doctor       Check host dependencies, config, and image agents
  status       Show runtime and image agent manifest
  uninstall    Remove Orcan; optional --purge-data / --purge-images (projects kept)
  version      Print version
  help         Show this help

Examples:
  orcan init                       # interactive wizard
  orcan init /absolute/path/to/repo
  orcan sync
  orcan up
  orcan enter
  orcan build --agent codex

Docs: https://akyther.github.io/orcan/latest/
Host:  bash + git + python3 (sync/wizard) + docker compose
EOF
}

main() {
    local cmd="${1:-help}"
    shift || true

    case "${cmd}" in
        -h | --help | help)
            # shellcheck source=commands/help.sh
            source "${ORCAN_CLI_DIR}/commands/help.sh"
            orcan_cmd_help "$@"
            ;;
        -V | --version | version)
            # shellcheck source=commands/version.sh
            source "${ORCAN_CLI_DIR}/commands/version.sh"
            orcan_cmd_version "$@"
            ;;
        init | sync | migrate | context | settings | studio | bundle | up | down | build | pull | publish | url | logs | seed | update | upgrade | downgrade | doctor | status | uninstall | enter | attach | go-in)
            local script=""
            case "${cmd}" in
                go-in) script="${ORCAN_CLI_DIR}/commands/enter.sh" ;;
                *) script="${ORCAN_CLI_DIR}/commands/${cmd}.sh" ;;
            esac
            if [[ ! -f "${script}" ]]; then
                orcan_usage_error "command not implemented: ${cmd}"
            fi
            # shellcheck disable=SC1090
            source "${script}"
            if [[ "${cmd}" == "go-in" ]]; then
                orcan_cmd_enter "$@"
            else
                "orcan_cmd_${cmd}" "$@"
            fi
            ;;
        *)
            orcan_usage_error "unknown command: ${cmd} (try: orcan help)"
            ;;
    esac
}

main "$@"
