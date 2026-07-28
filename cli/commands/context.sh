#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_context() {
    local sub="${1:-show}"
    shift || true
    orcan_require_python

    case "${sub}" in
        show)
            ORCAN_HOME="${ORCAN_HOME}" orcan_host_python "${ORCAN_SCRIPTS}/config-show.py" "$@"
            orcan_load_env
            if [[ -f "${ORCAN_ENV_FILE}" ]]; then
                printf '\n'
                printf 'Orchestrator home:      %s\n' "${ORCAN_HOME}"
                printf 'Install root:           %s\n' "${ORCAN_ROOT}"
                printf 'Workspace (container):  %s (%s)\n' \
                    "${WORKSPACE_ROOT:-${CONTAINER_PROJECT_DIR:-}}" "${WORKSPACE_NAME:-}"
                printf 'Runtime config:         %s\n' "${ORCAN_CONFIG_HOST:-${ORCAN_RUNTIME_DIR}/runtime-config.json}"
                printf 'Compose project mounts: %s\n' "${ORCAN_COMPOSE_PROJECTS:-${ORCAN_RUNTIME_DIR}/compose-projects.generated.yml}"
                if [[ -f "${ORCAN_COMPOSE_PROJECTS:-${ORCAN_RUNTIME_DIR}/compose-projects.generated.yml}" ]]; then
                    grep -E '^[[:space:]]+- ' "${ORCAN_COMPOSE_PROJECTS:-${ORCAN_RUNTIME_DIR}/compose-projects.generated.yml}" \
                        | sed 's/^/  /' || true
                fi
                printf 'Path parity:            enabled\n'
            fi
            ;;
        wizard)
            ORCAN_HOME="${ORCAN_HOME}" orcan_host_python "${ORCAN_SCRIPTS}/config-wizard.py" "$@"
            orcan_info "run: orcan sync"
            ;;
        add)
            local path="${1:-}"
            local workspace=""
            local force=""
            shift || true
            while [[ $# -gt 0 ]]; do
                case "$1" in
                    --workspace)
                        workspace="${2:-}"
                        shift 2 || orcan_usage_error "--workspace needs a value"
                        ;;
                    --force)
                        force=1
                        shift
                        ;;
                    *)
                        orcan_usage_error "unknown argument: $1"
                        ;;
                esac
            done
            if [[ -z "${path}" || "${path}" != /* ]]; then
                orcan_usage_error "usage: orcan context add /absolute/path/to/repo [--workspace NAME]"
            fi
            local args=(--project-dir "${path}" --config "${ORCAN_CONFIG_FILE}")
            if [[ -n "${workspace}" ]]; then
                args+=(--workspace "${workspace}")
            fi
            if [[ -n "${force}" ]]; then
                args+=(--force)
            fi
            ORCAN_HOME="${ORCAN_HOME}" orcan_host_python \
                "${ORCAN_SCRIPTS}/config-scaffold.py" "${args[@]}"
            orcan_info "run: orcan sync"
            ;;
        *)
            orcan_usage_error "usage: orcan context <show|wizard|add>"
            ;;
    esac
}
