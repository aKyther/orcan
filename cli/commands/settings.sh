#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_settings() {
    if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
        printf 'usage: orcan settings\n'
        printf '  Interactive: edit tool-level settings (tmux windows/prefix,\n'
        printf '  ttyd port/font) in orcan.config.json. Separate from `orcan init`\n'
        printf '  (workspaces/projects) — never touches workspace data.\n'
        printf '  After changing: orcan down && orcan up\n'
        return 0
    fi

    orcan_require_python
    if [[ ! -f "${ORCAN_CONFIG_FILE}" ]]; then
        orcan_die "no config found at ${ORCAN_CONFIG_FILE} — run 'orcan init' first"
    fi

    ORCAN_HOME="${ORCAN_HOME}" orcan_host_python \
        "${ORCAN_SCRIPTS}/settings-wizard.py" --config "${ORCAN_CONFIG_FILE}"
}
