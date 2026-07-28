#!/usr/bin/env bash
# Dependency checks for the orcan CLI.
# shellcheck shell=bash

orcan_have() {
    command -v "$1" >/dev/null 2>&1
}

orcan_require_cmd() {
    local name="$1"
    if ! orcan_have "${name}"; then
        orcan_die "required command not found: ${name}"
    fi
}

orcan_require_docker() {
    orcan_require_cmd docker
    if ! docker compose version >/dev/null 2>&1; then
        orcan_die "docker compose (v2) is required"
    fi
}

orcan_require_python() {
    orcan_require_cmd python3
}

orcan_require_git() {
    orcan_require_cmd git
}

orcan_host_python() {
    "${ORCAN_SCRIPTS}/python.sh" "$@"
}
