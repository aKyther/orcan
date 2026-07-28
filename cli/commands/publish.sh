#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_publish() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --claude | --cursor)
                orcan_die "publish is both-agents only (orcan:latest / orcan:<VERSION>) — not -claude/-cursor tags"
                ;;
            -h | --help)
                printf 'usage: orcan publish\n'
                printf '  Push local orcan:latest as registry :<VERSION> and :latest (both agents).\n'
                printf '  Does not publish orcan:<VERSION>-claude / -cursor. Not part of orcan build.\n'
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
