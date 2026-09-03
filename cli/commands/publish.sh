#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_publish() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h | --help)
                printf 'usage: orcan publish\n'
                printf '  Push local orcan:latest as registry :<VERSION> and :latest (all agents only).\n'
                printf '  The image manifest must enable every supported client. Not part of orcan build.\n'
                printf '  Login first: make registry-login\n'
                return 0
                ;;
            *)
                orcan_usage_error "unknown argument: $1"
                ;;
        esac
    done

    orcan_require_docker
    orcan_load_env
    orcan_image_publish
}
