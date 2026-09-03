#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_status() {
    local image="${IMAGE_LOCAL:-orcan:latest}" cname
    orcan_load_env 2>/dev/null || true
    cname="$(orcan_container_name)"
    printf 'orcan status\n\n'
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
