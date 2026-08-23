#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_up() {
    local with_docker=0
    local with_git=0
    local with_network=0
    local with_ttyd=0
    local network_name=""
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
            --with-network)
                if [[ $# -lt 2 || "$2" == -* ]]; then
                    orcan_usage_error "--with-network requires a network name"
                fi
                with_network=1
                network_name="$2"
                shift 2
                ;;
            --with-ttyd)
                with_ttyd=1
                shift
                ;;
            -h | --help)
                printf 'usage: orcan up [--with-ttyd] [--with-docker | --with-network NAME] [--with-git]\n'
                printf '  default: local-only container (orcan enter); no browser terminal\n'
                printf '  --with-ttyd: publish browser terminal (ttyd; TTYD_BIND defaults to loopback)\n'
                printf '  --with-docker | --with-network NAME: pick one (| = mutually exclusive)\n'
                printf '  --with-docker: mount /var/run/docker.sock (DinD)\n'
                printf '  --with-git: mount host ~/.ssh (+ agent) for push/pull (key exposure risk)\n'
                printf '  --with-network NAME: join an existing Docker network\n'
                printf '  --with-docker and --with-git expose credentials/capabilities to agents inside the container.\n'
                return 0
                ;;
            *)
                orcan_usage_error "unknown argument: $1"
                ;;
        esac
    done

    if (( with_docker && with_network )); then
        orcan_usage_error "--with-docker and --with-network are mutually exclusive (pick socket control or network reachability, not both)"
    fi

    orcan_require_docker
    orcan_require_generated
    orcan_load_env
    orcan_maybe_hint_update

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
    if (( with_network )); then
        if ! docker network inspect "${network_name}" >/dev/null 2>&1; then
            orcan_die "docker network '${network_name}' not found (create it first: docker network create ${network_name})"
        fi
        orcan_info "joining Docker network '${network_name}' (no socket, no host control)"
        orcan_write_network_overlay "${network_name}" >/dev/null
    fi

    # Stop the other overlay combo so volume mounts match the requested flags.
    orcan_compose_ttyd_down_all_variants

    local label="local-only"
    if (( with_ttyd )); then
        label="browser terminal"
    fi
    if (( with_docker )); then
        label="${label}, Docker socket enabled"
    fi
    if (( with_git )); then
        label="${label}, git/SSH enabled"
    fi
    if (( with_network )); then
        label="${label}, network '${network_name}' joined"
    fi

    if (( with_docker )); then
        if [[ ! -S /var/run/docker.sock ]]; then
            orcan_die "/var/run/docker.sock not found"
        fi
    fi

    orcan_info "starting container (${label})"
    orcan_compose_up_run "${with_docker}" "${with_git}" "${with_network}" "${with_ttyd}" up -d
    orcan_write_up_state "${with_docker}" "${with_git}" "${with_network}" "${with_ttyd}" "${network_name}"

    if (( with_docker )); then
        if ! orcan_compose_up_run "${with_docker}" "${with_git}" "${with_network}" "${with_ttyd}" exec -T orcan test -S /var/run/docker.sock 2>/dev/null; then
            orcan_warn "Docker socket missing in container; recreating…"
            orcan_compose_up_run "${with_docker}" "${with_git}" "${with_network}" "${with_ttyd}" up -d --force-recreate
            if ! orcan_compose_up_run "${with_docker}" "${with_git}" "${with_network}" "${with_ttyd}" exec -T orcan test -S /var/run/docker.sock 2>/dev/null; then
                orcan_die "/var/run/docker.sock is not mounted in the container"
            fi
        fi
    fi

    if (( with_git )); then
        if ! orcan_compose_up_run "${with_docker}" "${with_git}" "${with_network}" "${with_ttyd}" exec -T orcan test -d /home/developer/.ssh 2>/dev/null \
            && ! orcan_compose_up_run "${with_docker}" "${with_git}" "${with_network}" "${with_ttyd}" exec -T orcan test -S /run/host-ssh-agent.sock 2>/dev/null; then
            orcan_warn "git/SSH mounts missing in container; recreating…"
            orcan_compose_up_run "${with_docker}" "${with_git}" "${with_network}" "${with_ttyd}" up -d --force-recreate
        fi
    fi

    if (( with_network )); then
        local container_name
        container_name="$(orcan_container_name)"
        if ! docker network inspect "${network_name}" --format '{{range .Containers}}{{.Name}} {{end}}' 2>/dev/null \
            | grep -qw "${container_name}"; then
            orcan_warn "network '${network_name}' not attached; recreating…"
            orcan_compose_up_run "${with_docker}" "${with_git}" "${with_network}" "${with_ttyd}" up -d --force-recreate
            if ! docker network inspect "${network_name}" --format '{{range .Containers}}{{.Name}} {{end}}' 2>/dev/null \
                | grep -qw "${container_name}"; then
                orcan_die "container is not attached to network '${network_name}'"
            fi
        fi
    fi

    printf '\n'
    if (( with_ttyd )); then
        orcan_ok "browser terminal ready — open $(orcan_terminal_url)"
        printf '  Launcher → workspace → tmux\n'
    else
        orcan_ok "container ready — local access: orcan enter"
        printf '  Remote browser terminal: orcan up --with-ttyd\n'
    fi
    if [[ -n "${WORKSPACE_NAME:-}" ]]; then
        printf '  Workspace: %s\n' "${WORKSPACE_NAME}"
        printf '  Start dir (container): %s\n' "${WORKSPACE_ROOT:-${CONTAINER_PROJECT_DIR:-}}"
        orcan_require_python
        local hook_line hook_state
        hook_line="$(ORCAN_HOME="${ORCAN_HOME}" orcan_host_python "${ORCAN_SCRIPTS}/claude_hook.py" \
            status "${WORKSPACE_NAME}" --home "${ORCAN_HOME}" 2>/dev/null)" || true
        hook_state="${hook_line%% *}"
        printf '  Hook (Claude Stop: orcan-context-reflect): %s\n' "${hook_state:-unknown}"
        printf '  Toggle: orcan context hook enable|disable [WORKSPACE] [--all]\n'
    fi
    if (( with_git )); then
        printf '  Git/SSH: host ~/.ssh'
        if [[ -n "${SSH_AUTH_SOCK:-}" && -S "${SSH_AUTH_SOCK}" ]]; then
            printf ' + agent'
        fi
        printf ' (overlay: %s)\n' "${git_overlay}"
    fi
    if (( with_network )); then
        printf '  Docker network: %s\n' "${network_name}"
    fi
    printf '\nStop with: orcan down\n'
    if (( ! with_ttyd )); then
        printf 'Need a browser terminal?  orcan down && orcan up --with-ttyd\n'
    fi
    if (( ! with_git )); then
        printf 'Need git push/pull over SSH?  orcan up --with-git\n'
    fi
    if (( ! with_docker && ! with_network )); then
        printf 'Need Docker socket OR network reachability (pick one, not both)?\n'
        printf '  orcan up --with-docker          # control host Docker engine\n'
        printf '  orcan up --with-network NAME    # join an existing network only\n'
    elif (( ! with_docker )); then
        printf 'Need Docker-in-Docker?  orcan up --with-docker   (cannot combine with --with-network)\n'
    elif (( ! with_network )); then
        printf 'Need to reach containers on an existing Docker network?  orcan up --with-network NAME   (cannot combine with --with-docker)\n'
    fi
}
