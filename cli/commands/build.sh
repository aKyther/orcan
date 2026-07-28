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
                    orcan_usage_error "use only one of --claude / --cursor"
                fi
                variant="claude"
                force_local=1
                shift
                ;;
            --cursor)
                if [[ "${variant}" != "full" ]]; then
                    orcan_usage_error "use only one of --claude / --cursor"
                fi
                variant="cursor"
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
usage: orcan build [--claude|--cursor] [--no-cache|--force]

  Default (both agents):
    Tags: orcan:latest + orcan:<VERSION>
    1) Try pull registry orcan:<VERSION>
    2) On success → retag locally
    3) On miss → build both agents locally

  --claude / --cursor — install only that agent (no pull):
    Tags: orcan:<VERSION>-claude  or  orcan:<VERSION>-cursor
    Does not overwrite orcan:latest / orcan:<VERSION>.
    Then: IMAGE_LOCAL=orcan:<VERSION>-claude orcan up

  Never publishes. Maintainers push both-agents image: orcan publish
EOF
                return 0
                ;;
            *)
                orcan_usage_error "unknown argument: $1"
                ;;
        esac
    done

    orcan_require_docker
    if [[ ! -f "${ORCAN_ENV_FILE}" ]]; then
        orcan_die ".env missing — run: orcan sync (or orcan init /path/to/repo)"
    fi
    orcan_load_env

    if [[ "${variant}" == "full" ]] && (( ! force_local )); then
        if orcan_image_try_pull; then
            return 0
        fi
        orcan_info "no usable registry image — building both agents locally"
    fi

    orcan_image_build_local "${variant}" "${no_cache}"
}
