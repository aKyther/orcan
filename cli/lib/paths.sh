#!/usr/bin/env bash
# Resolve ORCAN_ROOT (install/clone) and ORCAN_HOME (user config + generated).
# shellcheck shell=bash

orcan_paths_init() {
    local self_dir

    if [[ -z "${ORCAN_ROOT:-}" ]]; then
        self_dir="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
        ORCAN_ROOT="${self_dir}"
    fi
    ORCAN_ROOT="$(cd -- "${ORCAN_ROOT}" && pwd)"

    if [[ -z "${ORCAN_HOME:-}" ]]; then
        # Always prefer XDG home for end users.
        # Opt into cwd only with ORCAN_HOME=… or ORCAN_USE_CWD=1 (legacy / experiments).
        if [[ "${ORCAN_USE_CWD:-}" == "1" && -f "${PWD}/orcan.config.json" ]]; then
            ORCAN_HOME="${PWD}"
        else
            ORCAN_HOME="${XDG_CONFIG_HOME:-${HOME}/.config}/orcan"
        fi
    fi
    if ! mkdir -p "${ORCAN_HOME}" 2>/dev/null; then
        orcan_warn "could not create ORCAN_HOME=${ORCAN_HOME} (check permissions)"
    fi
    if [[ -d "${ORCAN_HOME}" ]]; then
        ORCAN_HOME="$(cd -- "${ORCAN_HOME}" && pwd)"
    fi

    export ORCAN_ROOT ORCAN_HOME
    export ORCAN_CONFIG_FILE="${ORCAN_CONFIG_FILE:-${ORCAN_HOME}/orcan.config.json}"
    export ORCAN_RUNTIME_DIR="${ORCAN_RUNTIME_DIR:-${ORCAN_HOME}/mounts}"
    export ORCAN_DATA="${ORCAN_DATA:-${XDG_CONFIG_HOME:-${HOME}/.config}/orcan}"

    # Host scripts always live in the install/clone.
    export ORCAN_SCRIPTS="${ORCAN_ROOT}/scripts/repository"

    # One-time hint when a leftover config sits in cwd but we use XDG home.
    if [[ "${ORCAN_USE_CWD:-}" != "1" \
        && -f "${PWD}/orcan.config.json" \
        && "${PWD}" != "${ORCAN_HOME}" \
        && ! -f "${ORCAN_CONFIG_FILE}" ]]; then
        orcan_warn "found ${PWD}/orcan.config.json but using ORCAN_HOME=${ORCAN_HOME}"
        orcan_warn "move it with:  mkdir -p \"${ORCAN_HOME}\" && mv orcan.config.json \"${ORCAN_HOME}/\""
        orcan_warn "or force cwd:  ORCAN_USE_CWD=1 orcan …"
    fi
}

# The helper only emits known variable names and shell-quotes every JSON value.
# eval never sees user-authored shell source. Compose must not auto-load .env.
orcan_load_config() {
    if [[ "${_ORCAN_CONFIG_LOADED:-0}" == 1 ]]; then return 0; fi
    local exports
    exports="$(orcan_host_python "${ORCAN_SCRIPTS}/runtime-settings.py" --home "${ORCAN_HOME}" --config "${CONFIG:-${ORCAN_CONFIG_FILE}}")" || return
    eval "${exports}"
    export COMPOSE_DISABLE_ENV_FILE=1
    if [[ -n "${ORCAN_NAMED_INSTANCE:-}" ]]; then
        export ORCAN_INSTANCE="${ORCAN_NAMED_INSTANCE}"
        export COMPOSE_PROJECT_NAME="orcan-${ORCAN_NAMED_INSTANCE}"
    fi
    _ORCAN_CONFIG_LOADED=1
}

orcan_config_path() {
    if [[ -n "${CONFIG:-}" && -f "${CONFIG}" ]]; then
        printf '%s\n' "${CONFIG}"
        return 0
    fi
    if [[ -f "${ORCAN_CONFIG_FILE}" ]]; then
        printf '%s\n' "${ORCAN_CONFIG_FILE}"
        return 0
    fi
    return 1
}
