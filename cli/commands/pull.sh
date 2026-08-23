#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_pull() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h | --help)
                printf 'usage: orcan pull\n'
                printf '  Pull all-agents orcan:<VERSION> → orcan:latest.\n'
                printf '  Single-agent local tags: orcan build --claude / --cursor / --codex\n'
                return 0
                ;;
            --claude | --cursor | --codex)
                orcan_die "no registry tag for that — use: orcan build $1   → orcan:<VERSION>-${1#--}"
                ;;
            *)
                orcan_usage_error "unknown argument: $1"
                ;;
        esac
    done

    orcan_require_docker
    orcan_load_env
    if ! orcan_image_try_pull; then
        orcan_die "pull failed — run: orcan build   (builds the image locally; workspace edits only need orcan sync)"
    fi
}
