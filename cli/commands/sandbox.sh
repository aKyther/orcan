#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_sandbox() {
    orcan_require_python
    ORCAN_HOME="${ORCAN_HOME}" ORCAN_DATA="${ORCAN_DATA}" \
        ORCAN_CONFIG_FILE="${ORCAN_CONFIG_FILE}" \
        orcan_host_python "${ORCAN_SCRIPTS}/sandbox-pull.py" "$@"
}
