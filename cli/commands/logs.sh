#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_logs() {
    orcan_require_docker
    local cname
    cname="$(orcan_require_running_container)"
    docker logs -f "${cname}"
}
