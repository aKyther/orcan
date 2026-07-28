#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_down() {
    orcan_require_docker
    orcan_info "stopping containers"
    # Same Compose project regardless of overlays — try common flag combos.
    orcan_compose_ttyd_run 0 0 down >/dev/null 2>&1 || true
    orcan_compose_ttyd_run 1 0 down >/dev/null 2>&1 || true
    if [[ -f "$(orcan_compose_git_file)" ]]; then
        orcan_compose_ttyd_run 0 1 down >/dev/null 2>&1 || true
        orcan_compose_ttyd_run 1 1 down >/dev/null 2>&1 || true
    fi
    orcan_ok "stopped"
}
