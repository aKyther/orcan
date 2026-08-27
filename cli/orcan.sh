#!/usr/bin/env bash
# orcan CLI entry — dispatch to cli/commands/<name>.sh
set -Eeuo pipefail

ORCAN_CLI_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCAN_ROOT="$(cd -- "${ORCAN_CLI_DIR}/.." && pwd)"
export ORCAN_ROOT

# shellcheck source=lib/common.sh
source "${ORCAN_CLI_DIR}/lib/common.sh"

usage() {
    cat <<'EOF'
orcan — work-context orchestrator for coding agents

Usage:
  orcan <command> [arguments]

Commands:
  init         No PATH: TUI to create/edit workspaces + sync + show
               (--cli: old sequential prompt wizard instead)
               PATH: non-interactive scaffold (scripts/CI) + sync + show
  sync         Apply orcan.config.json → .env + mounts/* for Compose
  migrate      Move projects under the managed root (fewer future recreates)
  context      Manage context (show | add | tui | worktrees | worktree | assert | hook)
  settings     Edit tool settings (tmux, ttyd) — separate from workspaces
  up           Start container (orcan enter; --with-ttyd | --with-ttyd-auth for browser)
  down         Stop containers
  build        All agents → orcan:latest + orcan:<VERSION> (pull or build)
               (--claude/--cursor/--codex → orcan:<VERSION>-claude|cursor|codex, no pull)
  pull         Pull all-agents orcan:<VERSION> → orcan:latest
  publish      Manual push of both-agents orcan:latest (not part of build)
  url          Print browser terminal URL
  logs         Follow container logs
  enter        Local terminal into the container (alias: go-in)
  update       Checkout newest release tag (--main / --to VERSION)
  downgrade    Previous release (or --to VERSION)
  doctor       Check host dependencies and config
  uninstall    Remove the CLI install (optional --purge-data)
  version      Print version
  help         Show this help

Examples:
  orcan init                       # interactive wizard
  orcan init /absolute/path/to/repo
  orcan sync
  orcan up
  orcan enter
  orcan build

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
        init | sync | migrate | context | settings | up | down | build | pull | publish | url | logs | seed | update | downgrade | doctor | uninstall | enter | go-in)
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
