#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_init() {
    local project_dir="${1:-}"
    local workspace="${WORKSPACE:-}"

    if [[ "${project_dir}" == "-h" || "${project_dir}" == "--help" ]]; then
        printf 'usage: orcan init [PATH]\n'
        printf '  No PATH: interactive config wizard — create orcan.config.json, or edit it\n'
        printf '           if one already exists (add/remove workspaces and projects).\n'
        printf '  PATH:    non-interactive — scaffold a single-project config from PATH,\n'
        printf '           for scripts/CI (skips the wizard).\n'
        printf '  Either way, finishes with orcan sync.\n'
        return 0
    fi

    orcan_require_python
    orcan_ensure_home_env_example
    mkdir -p "${ORCAN_HOME}"

    if [[ -z "${project_dir}" ]]; then
        ORCAN_HOME="${ORCAN_HOME}" orcan_host_python "${ORCAN_SCRIPTS}/config-wizard.py"
    else
        if [[ "${project_dir}" != /* ]]; then
            orcan_usage_error "path must be absolute: ${project_dir}"
        fi
        if [[ ! -d "${project_dir}" ]]; then
            orcan_die "not a directory: ${project_dir}"
        fi
        orcan_info "scaffolding workspace for ${project_dir}"
        local args=(--project-dir "${project_dir}" --config "${ORCAN_CONFIG_FILE}")
        if [[ -n "${workspace}" ]]; then
            args+=(--workspace "${workspace}")
        fi
        ORCAN_HOME="${ORCAN_HOME}" orcan_host_python \
            "${ORCAN_SCRIPTS}/config-scaffold.py" "${args[@]}"
    fi

    # shellcheck source=sync.sh
    source "$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sync.sh"
    orcan_cmd_sync
    ORCAN_HOME="${ORCAN_HOME}" orcan_host_python "${ORCAN_SCRIPTS}/config-show.py" || true
    orcan_ok "init done"
    orcan_info "next: orcan build && orcan up"
}
