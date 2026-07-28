#!/usr/bin/env bash
# Shared logging for the orcan CLI.
# shellcheck shell=bash

orcan_log_init() {
    if [[ -n "${ORCAN_NO_COLOR:-}" ]] || [[ ! -t 2 ]]; then
        ORCAN_CLR_RESET=""
        ORCAN_CLR_BOLD=""
        ORCAN_CLR_DIM=""
        ORCAN_CLR_RED=""
        ORCAN_CLR_GREEN=""
        ORCAN_CLR_YELLOW=""
        ORCAN_CLR_CYAN=""
    else
        ORCAN_CLR_RESET=$'\033[0m'
        ORCAN_CLR_BOLD=$'\033[1m'
        ORCAN_CLR_DIM=$'\033[2m'
        ORCAN_CLR_RED=$'\033[31m'
        ORCAN_CLR_GREEN=$'\033[32m'
        ORCAN_CLR_YELLOW=$'\033[33m'
        ORCAN_CLR_CYAN=$'\033[36m'
    fi
}

orcan_info() {
    printf '%s%s%s %s\n' "${ORCAN_CLR_CYAN}" "orcan:" "${ORCAN_CLR_RESET}" "$*"
}

orcan_ok() {
    printf '%s%s%s %s\n' "${ORCAN_CLR_GREEN}" "orcan:" "${ORCAN_CLR_RESET}" "$*"
}

orcan_warn() {
    printf '%s%s%s %s\n' "${ORCAN_CLR_YELLOW}" "orcan:" "${ORCAN_CLR_RESET}" "$*" >&2
}

orcan_error() {
    printf '%s%s%s %s\n' "${ORCAN_CLR_RED}" "orcan:" "${ORCAN_CLR_RESET}" "$*" >&2
}

orcan_die() {
    orcan_error "$*"
    exit 1
}

orcan_usage_error() {
    orcan_error "$*"
    exit 2
}
