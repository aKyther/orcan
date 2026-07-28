#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_version() {
    local ver="dev"
    if [[ -f "${ORCAN_ROOT}/VERSION" ]]; then
        ver="$(tr -d '[:space:]' < "${ORCAN_ROOT}/VERSION")"
    fi
    printf 'orcan %s\n' "${ver}"
    printf 'root: %s\n' "${ORCAN_ROOT}"
    printf 'home: %s\n' "${ORCAN_HOME}"
}
