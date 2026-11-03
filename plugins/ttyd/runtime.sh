#!/usr/bin/env bash
# shellcheck shell=bash


orcan_plugin_ttyd_prepare() {
    if [[ "${TTYD_AUTHENTICATION:-none}" == basic ]] && ((!with_ttyd_auth)) && [[ -z "${TTYD_CREDENTIAL:-}" ]]; then
        orcan_die "ttyd basic authentication requires process TTYD_CREDENTIAL or --web-terminal-auth USER:PASS"
        return 1
    fi
    if ((with_ttyd_auth)); then
        local traced=0
        if [[ $- == *x* ]]; then traced=1; set +x; fi
        export TTYD_CREDENTIAL="${ttyd_credential}"
        if ((traced)); then set -x; fi
    fi
}
orcan_plugin_ttyd_report() {
    orcan_ok "browser terminal ready — open $(orcan_terminal_url)"
}
