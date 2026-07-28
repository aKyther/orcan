#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_init() {
    local project_dir="${1:-}"
    local workspace="${WORKSPACE:-}"

    orcan_require_python
    orcan_ensure_home_env_example
    mkdir -p "${ORCAN_HOME}"

    if [[ -z "${project_dir}" ]]; then
        if [[ -f "${ORCAN_CONFIG_FILE}" ]]; then
            orcan_info "using existing ${ORCAN_CONFIG_FILE}"
        else
            orcan_usage_error "usage: orcan init /absolute/path/to/repo"
        fi
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
