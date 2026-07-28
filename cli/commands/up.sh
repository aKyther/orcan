#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_up() {
    local with_docker=0
    local with_git=0
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
            --with-git)
                with_git=1
                shift
                ;;
            -h | --help)
                printf 'usage: orcan up [--with-docker] [--with-git]\n'
                printf '  default: browser terminal without Docker socket or host SSH\n'
                printf '  --with-docker: mount /var/run/docker.sock (DinD; host control risk)\n'
                printf '  --with-git: mount host ~/.ssh (+ agent) for push/pull (key exposure risk)\n'
                printf '  Both flags expose credentials/capabilities to agents inside the container.\n'
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
    orcan_maybe_hint_update

    local port="${TTYD_HOST_PORT:-7681}"
    local git_overlay=""

    if (( with_git )); then
        git_overlay="$(orcan_write_git_overlay)"
    fi

    if (( with_docker )); then
        orcan_warn "SECURITY: --with-docker mounts the host Docker socket into the container."
        orcan_warn "  Agents/tools inside can control the host Docker engine (full host reach)."
    fi
    if (( with_git )); then
        orcan_warn "SECURITY: --with-git mounts host ~/.ssh (and SSH agent if set) into the container."
        orcan_warn "  Agents/tools inside can use those keys for git push and other SSH access."
    fi
    if (( with_docker || with_git )); then
        orcan_warn "  Prefer plain \`orcan up\` unless you need these capabilities."
    fi

    # Stop the other overlay combo so volume mounts match the requested flags.
    orcan_compose_ttyd_run 0 0 down >/dev/null 2>&1 || true
    orcan_compose_ttyd_run 1 0 down >/dev/null 2>&1 || true
    if [[ -f "$(orcan_compose_git_file)" ]]; then
        orcan_compose_ttyd_run 0 1 down >/dev/null 2>&1 || true
        orcan_compose_ttyd_run 1 1 down >/dev/null 2>&1 || true
    fi

    local label="no Docker socket"
    if (( with_docker )); then
        label="Docker socket enabled"
    fi
    if (( with_git )); then
        label="${label}, git/SSH enabled"
    fi

    if (( with_docker )); then
        if [[ ! -S /var/run/docker.sock ]]; then
            orcan_die "/var/run/docker.sock not found"
        fi
    fi

    orcan_info "starting terminal (${label})"
    orcan_compose_ttyd_run "${with_docker}" "${with_git}" up -d

    if (( with_docker )); then
        if ! orcan_compose_ttyd_run "${with_docker}" "${with_git}" exec -T orcan test -S /var/run/docker.sock 2>/dev/null; then
            orcan_warn "Docker socket missing in container; recreating…"
            orcan_compose_ttyd_run "${with_docker}" "${with_git}" up -d --force-recreate
            if ! orcan_compose_ttyd_run "${with_docker}" "${with_git}" exec -T orcan test -S /var/run/docker.sock 2>/dev/null; then
                orcan_die "/var/run/docker.sock is not mounted in the container"
            fi
        fi
    fi

    if (( with_git )); then
        if ! orcan_compose_ttyd_run "${with_docker}" "${with_git}" exec -T orcan test -d /home/developer/.ssh 2>/dev/null \
            && ! orcan_compose_ttyd_run "${with_docker}" "${with_git}" exec -T orcan test -S /run/host-ssh-agent.sock 2>/dev/null; then
            orcan_warn "git/SSH mounts missing in container; recreating…"
            orcan_compose_ttyd_run "${with_docker}" "${with_git}" up -d --force-recreate
        fi
    fi

    printf '\n'
    orcan_ok "terminal ready — open http://localhost:${port}"
    printf '  Launcher → workspace → tmux\n'
    if [[ -n "${WORKSPACE_NAME:-}" ]]; then
        printf '  Workspace: %s\n' "${WORKSPACE_NAME}"
        printf '  Start dir (container): %s\n' "${WORKSPACE_ROOT:-${CONTAINER_PROJECT_DIR:-}}"
    fi
    if (( with_git )); then
        printf '  Git/SSH: host ~/.ssh'
        if [[ -n "${SSH_AUTH_SOCK:-}" && -S "${SSH_AUTH_SOCK}" ]]; then
            printf ' + agent'
        fi
        printf ' (overlay: %s)\n' "${git_overlay}"
    fi
    printf '\nStop with: orcan down\n'
    if (( ! with_docker )); then
        printf 'Need Docker-in-Docker?  orcan up --with-docker\n'
    fi
    if (( ! with_git )); then
        printf 'Need git push/pull over SSH?  orcan up --with-git\n'
    fi
}
