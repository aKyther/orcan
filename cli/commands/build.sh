#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_build() {
    local variant="full"
    local no_cache=0
    local force_local=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --claude)
                if [[ "${variant}" != "full" ]]; then
                    orcan_usage_error "use only one of --claude / --cursor / --codex"
                fi
                variant="claude"
                force_local=1
                shift
                ;;
            --cursor)
                if [[ "${variant}" != "full" ]]; then
                    orcan_usage_error "use only one of --claude / --cursor / --codex"
                fi
                variant="cursor"
                force_local=1
                shift
                ;;
            --codex)
                if [[ "${variant}" != "full" ]]; then
                    orcan_usage_error "use only one of --claude / --cursor / --codex"
                fi
                variant="codex"
                force_local=1
                shift
                ;;
            --no-cache)
                no_cache=1
                force_local=1
                shift
                ;;
            --force | --no-pull)
                force_local=1
                shift
                ;;
            --no-publish)
                orcan_warn "--no-publish is obsolete (build never publishes; use: orcan publish)"
                shift
                ;;
            -h | --help)
                cat <<'EOF'
usage: orcan build [--claude|--cursor|--codex] [--no-cache|--force]

  Default (all agents):
    Tags: orcan:latest + orcan:<VERSION>
    1) Try pull registry orcan:<VERSION>
    2) On success → retag locally
    3) On miss → build all agents locally

  --claude / --cursor / --codex — install only that agent (no pull):
    Tags: orcan:<VERSION>-claude / -cursor / -codex
    Does not overwrite orcan:latest / orcan:<VERSION>.
    Then: IMAGE_LOCAL=orcan:<VERSION>-claude orcan up

  Never publishes. Maintainers push the all-agents image: orcan publish
EOF
                return 0
                ;;
            *)
                orcan_usage_error "unknown argument: $1"
                ;;
        esac
    done

    orcan_require_docker
    orcan_require_env_for_build
    orcan_load_env
    orcan_runtime_warn_if_config_stale build

    if [[ "${variant}" == "full" ]] && (( ! force_local )); then
        if orcan_image_try_pull; then
            return 0
        fi
        orcan_info "no usable registry image — building all agents locally"
    fi

    orcan_image_build_local "${variant}" "${no_cache}"
}
