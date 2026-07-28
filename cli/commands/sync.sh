#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_sync() {
    orcan_require_python
    orcan_ensure_home_env_example
    mkdir -p "${ORCAN_HOME}" "${ORCAN_RUNTIME_DIR}"

    local cfg=""
    if cfg="$(orcan_config_path)"; then
        :
    else
        cfg=""
    fi

    orcan_info "syncing config → ${ORCAN_HOME}"
    CONFIG="${cfg}" \
        PROJECT_DIR="${PROJECT_DIR:-${ORCAN_HOME}}" \
        ORCAN_HOME="${ORCAN_HOME}" \
        ORCAN_ROOT="${ORCAN_ROOT}" \
        "${ORCAN_SCRIPTS}/update-env.sh"

    orcan_ok "sync complete"
    orcan_info "next: orcan up"
}
