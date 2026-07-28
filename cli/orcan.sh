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
  init         First-run setup (scaffold config, sync, show)
  sync         Apply orcan.config.json → .env + .orcan/* for Compose
  context      Manage context (show | wizard | add)
  up           Start browser terminal (--with-docker / --with-git)
  down         Stop containers
  build        Both agents → orcan:latest + orcan:<VERSION> (pull or build)
               (--claude/--cursor → orcan:<VERSION>-claude|cursor, no pull)
  pull         Pull both-agents orcan:<VERSION> → orcan:latest
  publish      Manual push of both-agents orcan:latest (not part of build)
  url          Print browser terminal URL
  logs         Follow container logs
  enter        Local terminal into the container (alias: go-in)
  update       Checkout newest release tag (or --main)
  doctor       Check host dependencies and config
  uninstall    Remove the CLI install (optional --purge-data)
  version      Print version
  help         Show this help

Examples:
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
        init | sync | context | up | down | build | pull | publish | url | logs | seed | update | doctor | uninstall | enter | go-in)
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
