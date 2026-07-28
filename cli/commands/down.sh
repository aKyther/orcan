#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_down() {
    orcan_require_docker
    orcan_info "stopping containers"
    orcan_compose_ttyd down >/dev/null 2>&1 || true
    orcan_compose_ttyd_docker down >/dev/null 2>&1 || true
    orcan_ok "stopped"
}
