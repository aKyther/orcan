#!/usr/bin/env bash
# shellcheck shell=bash


orcan_plugin_docker_prepare() {
    [[ -S /var/run/docker.sock ]] || { orcan_die "/var/run/docker.sock not found"; return 1; }
    orcan_warn "Docker plugin exposes control of the host Docker engine to the container."
}
orcan_plugin_docker_verify() {
    if ! orcan_run_selected exec -T orcan test -S /var/run/docker.sock 2>/dev/null; then
        orcan_run_selected up -d --force-recreate || return
        orcan_run_selected exec -T orcan test -S /var/run/docker.sock 2>/dev/null || {
            orcan_die "/var/run/docker.sock is not mounted in the container"
            return 1
        }
    fi
}
