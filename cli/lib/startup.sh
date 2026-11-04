#!/usr/bin/env bash
# One startup pipeline. Receipts describe completed images, never auth values.
# shellcheck shell=bash

orcan_startup_stage() {
    orcan_info "startup: $1"
    orcan_host_python "${ORCAN_SCRIPTS}/startup-state.py" status \
        --file "${ORCAN_RUNTIME_DIR}/startup.json" --stage "$1"
}

orcan_startup_prepare() {
    orcan_startup_stage prepare || return
    orcan_load_config || return
    local runtime mounts
    runtime="$(orcan_runtime_config_json_file)"
    mounts="$(orcan_runtime_compose_mounts_file)"
    if [[ ! -f "${runtime}" || ! -f "${mounts}" ]] || orcan_runtime_config_is_stale; then
        source "${ORCAN_ROOT}/cli/commands/sync.sh"
        ORCAN_STARTUP_PREPARE=1 orcan_cmd_sync || return
    fi
    orcan_require_generated || return
    orcan_startup_stage image || return
    local cfg profile fingerprint image_id
    cfg="$(orcan_config_path)" || cfg=""
    profile="$(orcan_host_python "${ORCAN_SCRIPTS}/image-profile.py" --config "${cfg}")" || return
    fingerprint="$(orcan_host_python "${ORCAN_SCRIPTS}/startup-state.py" fingerprint \
        --root "${ORCAN_ROOT}" --profile "${profile}" \
        --identity "${USER_UID:-$(id -u)}:${USER_GID:-$(id -g)}:${DOCKER_GID:-999}")" || return
    image_id="$(docker image inspect --format '{{.Id}}' "${IMAGE_LOCAL:-orcan:latest}" 2>/dev/null)" || image_id=""
    if [[ -n "${image_id}" ]] && orcan_host_python "${ORCAN_SCRIPTS}/startup-state.py" matches \
        --file "${ORCAN_RUNTIME_DIR}/image-ready.json" --fingerprint "${fingerprint}" --image-id "${image_id}"; then
        orcan_info 'using completed image build'
    else
        source "${ORCAN_ROOT}/cli/commands/build.sh"
        orcan_cmd_build || return
        image_id="$(docker image inspect --format '{{.Id}}' "${IMAGE_LOCAL:-orcan:latest}")" || return
        orcan_host_python "${ORCAN_SCRIPTS}/startup-state.py" record \
            --file "${ORCAN_RUNTIME_DIR}/image-ready.json" --fingerprint "${fingerprint}" --image-id "${image_id}" || return
    fi
}

orcan_startup_verify() {
    local state
    state="$(docker inspect --format '{{.State.Running}}' "$(orcan_container_name)")" || return
    [[ "${state}" == true ]] || { orcan_warn 'container exited during startup'; return 1; }
    orcan_plugins_run verify
}
