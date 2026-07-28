#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_seed() {
    local all=0
    local dry=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --all)
                all=1
                shift
                ;;
            --dry-run)
                dry=1
                shift
                ;;
            -h | --help)
                printf 'usage: orcan seed [--all] [--dry-run]\n'
                printf '  Optional: copy Cursor/Claude templates into git checkouts.\n'
                printf '  Not required — the workspace context pack is created on container start.\n'
                return 0
                ;;
            *)
                orcan_usage_error "unknown argument: $1"
                ;;
        esac
    done

    orcan_require_docker
    orcan_require_generated
    orcan_load_env

    if (( all )); then
        if (( dry )); then
            orcan_compose_base run --rm --name orcan-init-projects-dry orcan orcan-init-projects --dry-run
        else
            orcan_compose_base run --rm --name orcan-init-projects orcan orcan-init-projects
        fi
    else
        local target="${PROJECT_DIR:-}"
        if [[ -z "${target}" ]]; then
            orcan_die "PROJECT_DIR unset — run orcan sync, or use: orcan seed --all"
        fi
        if (( dry )); then
            orcan_compose_base run --rm --name orcan-init-project-dry orcan \
                cursor-init-project --dry-run "${target}"
        else
            orcan_compose_base run --rm --name orcan-init-project orcan \
                cursor-init-project "${target}"
        fi
    fi
}
