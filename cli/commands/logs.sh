#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_logs() {
    orcan_require_docker
    if orcan_compose_ttyd_docker ps -q orcan 2>/dev/null | grep -q .; then
        orcan_compose_ttyd_docker logs -f
    elif orcan_compose_ttyd ps -q orcan 2>/dev/null | grep -q .; then
        orcan_compose_ttyd logs -f
    else
        orcan_die "no running container — start with: orcan up"
    fi
}
