#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_settings() {
    local script=settings_tui.py
    case "${1:-}" in
        --help|-h)
            printf 'usage: orcan settings [--cli]\n'
            printf '  TUI: workspaces, startup plugins, installed agent CLIs, container and tmux settings.\n'
            printf '  Review and explicitly save one orcan.config.json. No build/start happens on save.\n'
            printf '  --cli: use the sequential settings wizard instead.\n'
            return 0 ;;
        --cli) script=settings-wizard.py; shift ;;
    esac
    [[ $# -eq 0 ]] || { orcan_usage_error 'usage: orcan settings [--cli]'; return 2; }
    orcan_require_python
    [[ -f "${ORCAN_CONFIG_FILE}" ]] || { orcan_die "no config found at ${ORCAN_CONFIG_FILE} — run 'orcan init' first"; return 1; }
    ORCAN_HOME="${ORCAN_HOME}" orcan_host_python "${ORCAN_SCRIPTS}/${script}" --config "${ORCAN_CONFIG_FILE}"
}
