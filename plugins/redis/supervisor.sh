#!/usr/bin/env bash
# shellcheck shell=bash
# Sourcing defines this trusted container lifecycle hook only.

orcan_plugin_redis_supervisor() {
    [[ "${ORCAN_REDIS_ENABLED:-0}" == "1" ]] || return 0
    local package programs program
    package="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    programs="$("${ORCAN_SUPERVISOR_PYTHON:-/opt/orcan-executor/venv/bin/python}" "${package}/supervisor.py")" || return
    while IFS= read -r program; do
        install_program "${package}/supervisor.d/${program}.conf" || return
    done <<<"${programs}"
}
