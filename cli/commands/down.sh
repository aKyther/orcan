#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_down() {
    orcan_require_docker
    orcan_info "stopping containers"
    # Same Compose project regardless of overlays — try every combo that up.sh could have used.
    orcan_compose_ttyd_down_all_variants
    orcan_ok "stopped"
}
