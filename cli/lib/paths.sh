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
            ORCAN_HOME="${XDG_CONFIG_HOME:-${HOME}/.config}/orcan/home"
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
    export ORCAN_ENV_FILE="${ORCAN_ENV_FILE:-${ORCAN_HOME}/.env}"
    export ORCAN_RUNTIME_DIR="${ORCAN_RUNTIME_DIR:-${ORCAN_HOME}/.orcan}"
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

orcan_ensure_home_env_example() {
    if [[ ! -f "${ORCAN_HOME}/.env.example" ]]; then
        if [[ -f "${ORCAN_ROOT}/.env.example" ]]; then
            cp -- "${ORCAN_ROOT}/.env.example" "${ORCAN_HOME}/.env.example"
        fi
    fi
}

orcan_load_env() {
    if [[ ! -r "${ORCAN_ENV_FILE}" ]]; then
        return 0
    fi
    set -a
    # shellcheck disable=SC1090
    source "${ORCAN_ENV_FILE}" || true
    set +a
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
