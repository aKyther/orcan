#!/usr/bin/env bash
# Shared lifecycle for the installed, bundled plugin catalog.
# shellcheck shell=bash

orcan_plugins_run() {
    local phase="$1" plugin hook
    for plugin in ${ORCAN_ACTIVE_PLUGINS:-}; do
        # IDs come exclusively from plugin-plan.py's validated bundled catalog.
        [[ "${plugin}" =~ ^[a-z][a-z0-9-]*$ ]] || return 1
        # shellcheck disable=SC1090
        source "${ORCAN_ROOT}/plugins/${plugin}/runtime.sh" || return
        hook="orcan_plugin_${plugin//-/_}_${phase}"
        if declare -F "${hook}" >/dev/null; then "${hook}" || return; fi
    done
}

orcan_run_selected() {
    # Applies also to plugin verification/recreate retries.
    if [[ "${1:-}" == up ]]; then
        set -- "$@" --no-build --pull never
    fi
    orcan_compose_up_run "${with_docker}" "${with_git}" "${with_network}" \
        "${with_ttyd}" "${with_github}" "${with_gitlab}" "$@"
}
