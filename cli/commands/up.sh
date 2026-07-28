#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_up() {
    local with_docker=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --with-docker)
                with_docker=1
                shift
                ;;
            --no-docker)
                # Backward-compatible alias (default is already without socket).
                with_docker=0
                shift
                ;;
            -h | --help)
                printf 'usage: orcan up [--with-docker]\n'
                printf '  default: browser terminal without Docker socket\n'
                printf '  --with-docker: mount /var/run/docker.sock (DinD)\n'
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

    local port="${TTYD_HOST_PORT:-7681}"

    if (( with_docker )); then
        if [[ ! -S /var/run/docker.sock ]]; then
            orcan_die "/var/run/docker.sock not found"
        fi
        orcan_compose_ttyd down >/dev/null 2>&1 || true
        orcan_info "starting terminal (Docker socket enabled)"
        orcan_compose_ttyd_docker up -d
        if ! orcan_compose_ttyd_docker exec -T orcan test -S /var/run/docker.sock 2>/dev/null; then
            orcan_warn "Docker socket missing in container; recreating…"
            orcan_compose_ttyd_docker up -d --force-recreate
            if ! orcan_compose_ttyd_docker exec -T orcan test -S /var/run/docker.sock 2>/dev/null; then
                orcan_die "/var/run/docker.sock is not mounted in the container"
            fi
        fi
    else
        orcan_compose_ttyd_docker down >/dev/null 2>&1 || true
        orcan_info "starting terminal (no Docker socket)"
        orcan_compose_ttyd up -d
    fi

    printf '\n'
    orcan_ok "terminal ready — open http://localhost:${port}"
    printf '  Launcher → workspace → tmux\n'
    if [[ -n "${WORKSPACE_NAME:-}" ]]; then
        printf '  Workspace: %s\n' "${WORKSPACE_NAME}"
        printf '  Start dir (container): %s\n' "${WORKSPACE_ROOT:-${CONTAINER_PROJECT_DIR:-}}"
    fi
    printf '\nStop with: orcan down\n'
    if (( ! with_docker )); then
        printf 'Need Docker-in-Docker?  orcan up --with-docker\n'
    fi
}
