#!/usr/bin/env bash
# Start prepared inputs only. Sync and build are explicit commands.
# shellcheck shell=bash

orcan_startup_stage() {
    orcan_info "startup: $1"
    orcan_host_python "${ORCAN_SCRIPTS}/startup-state.py" status \
        --file "${ORCAN_RUNTIME_DIR}/startup.json" --stage "$1"
}

orcan_startup_check_inputs() {
    orcan_load_config || return
    orcan_require_generated || return
    if ! docker image inspect --format '{{.Id}}' "${IMAGE_LOCAL:-orcan:latest}" >/dev/null 2>&1; then
        orcan_warn "local image unavailable: ${IMAGE_LOCAL:-orcan:latest}; check Docker, then run orcan build (or explicitly orcan pull) if needed"
        return 1
    fi
}

orcan_startup_verify() {
    local state
    state="$(docker inspect --format '{{.State.Running}}' "$(orcan_container_name)")" || return
    [[ "${state}" == true ]] || { orcan_warn 'container exited during startup'; return 1; }
    orcan_plugins_run verify
}
