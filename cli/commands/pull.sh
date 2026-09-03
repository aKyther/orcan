#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_pull() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h | --help)
                printf 'usage: orcan pull\n'
                printf '  Pull the portable all-agents orcan:<VERSION> → orcan:latest.\n'
                printf '  Local partial images: orcan build --agent NAME.\n'
                return 0
                ;;
            *)
                orcan_usage_error "unknown argument: $1"
                ;;
        esac
    done

    orcan_require_docker
    orcan_load_env
    if ! orcan_image_try_pull; then
        orcan_die "pull failed — run: orcan build --all-agents   (workspace edits only need orcan sync)"
    fi
}
