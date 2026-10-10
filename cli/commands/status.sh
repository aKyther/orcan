#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_status() {
    local image="${IMAGE_LOCAL:-orcan:latest}" cname ver
    orcan_load_env 2>/dev/null || true
    cname="$(orcan_container_name)"
    ver="$(orcan_image_version)"
    printf 'orcan status\n\n'
    printf 'version: %s\n' "${ver}"
    printf 'installation (ORCAN_ROOT): %s\n' "${ORCAN_ROOT}"
    printf 'config home (ORCAN_HOME): %s\n' "${ORCAN_HOME}"
    printf 'data (ORCAN_DATA): %s\n' "${ORCAN_DATA}"
    printf 'config file: %s\n' "${ORCAN_CONFIG_FILE}"
    if orcan_have docker && docker image inspect "${image}" >/dev/null 2>&1; then
        printf 'image: %s\n' "${image}"
        printf 'agents: '
        docker run --rm --entrypoint cat "${image}" /etc/orcan/agents.json 2>/dev/null \
            || printf 'unknown (rebuild with: orcan build --agent codex)\n'
    else
        printf 'image: missing (%s)\n' "${image}"
    fi
    if orcan_have docker && orcan_container_is_running "${cname}"; then
        printf 'container: %s (running)\n' "${cname}"
    else
        printf 'container: %s (stopped)\n' "${cname}"
    fi
}
