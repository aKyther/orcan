#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_up() {
    local with_docker=0
    local with_git=0
    local with_github=0
    local github_hostname=""
    local ORCAN_GITHUB_TOKEN=""
    export ORCAN_GITHUB_TOKEN
    local with_network=0
    local with_ttyd=0
    local with_ttyd_opt=0
    local with_ttyd_auth=0
    local network_name=""
    local ttyd_credential=""
    local resume=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --docker-socket | --with-docker)
                with_docker=1
                shift
                ;;
            --no-docker)
                # Backward-compatible alias (default is already without socket).
                with_docker=0
                shift
                ;;
            --ssh | --with-git)
                with_git=1
                shift
                ;;
            --network | --with-network)
                if [[ $# -lt 2 || "$2" == -* ]]; then
                    orcan_usage_error "--network requires a network name"
                fi
                with_network=1
                network_name="$2"
                shift 2
                ;;
            --web-terminal | --with-ttyd)
                with_ttyd=1
                with_ttyd_opt=1
                shift
                ;;
            --web-terminal-auth | --with-ttyd-auth)
                if [[ $# -lt 2 || "$2" == -* ]]; then
                    orcan_usage_error "--web-terminal-auth requires user:password"
                fi
                with_ttyd_auth=1
                with_ttyd=1
                ttyd_credential="$2"
                shift 2
                ;;
            --github)
                with_github=1
                shift
                ;;
            --github-hostname)
                [[ $# -ge 2 && -n "$2" && "$2" != -* ]] || orcan_usage_error '--github-hostname requires a hostname'
                github_hostname="$2"
                shift 2
                ;;
            --resume)
                resume=1
                shift
                ;;
            -h | --help)
                printf 'usage: orcan up --resume [--web-terminal-auth USER:PASS]\n'
                printf '       orcan up [--web-terminal | --web-terminal-auth USER:PASS] [--docker-socket | --network NAME] [--ssh] [--github [--github-hostname HOST]]\n'
                printf '  default: local-only container (orcan enter); no browser terminal\n'
                printf '  --web-terminal | --web-terminal-auth USER:PASS: pick one (| = mutually exclusive)\n'
                printf '  --web-terminal: publish browser terminal, no password prompt\n'
                printf '  --web-terminal-auth USER:PASS: publish browser terminal with HTTP basic auth\n'
                printf '  --docker-socket | --network NAME: pick one (| = mutually exclusive)\n'
                printf '  --docker-socket: mount /var/run/docker.sock (DinD)\n'
                printf '  --ssh: mount host ~/.ssh (+ agent) for push/pull (key exposure risk)\n'
                printf '  --network NAME: join an existing Docker network\n'
                printf '  --github: provide GitHub authentication (GH_TOKEN or gh auth login)\n'
                printf '  --github-hostname HOST: GitHub host (default: github.com; Enterprise Server uses GH_ENTERPRISE_TOKEN)\n'
                printf '  Compatibility aliases: --with-git, --with-docker, --with-network, --with-ttyd, --with-ttyd-auth\n'
                printf '  --resume: restart with the flags of the last orcan up (kept across orcan down)\n'
                printf '  --docker-socket and --ssh expose credentials/capabilities to agents inside the container.\n'
                return 0
                ;;
            *)
                orcan_usage_error "unknown argument: $1"
                ;;
        esac
    done

    if (( resume )); then
        if ((with_docker || with_git || with_github || with_network || with_ttyd_opt || ${#github_hostname})); then
            orcan_usage_error "--resume restores saved flags; only --web-terminal-auth may be passed with it"
        fi
        orcan_load_env
        local last_up
        last_up="$(orcan_last_up_file)"
        [[ -f "${last_up}" ]] || orcan_die "no previous orcan up recorded (${last_up}) — start with explicit flags"
        # shellcheck disable=SC1090
        local WITH_GITHUB=0 GITHUB_HOSTNAME=""
        source "${last_up}"
        with_docker="${WITH_DOCKER:-0}"
        with_git="${WITH_GIT:-0}"
        with_github="${WITH_GITHUB:-0}"
        github_hostname="${GITHUB_HOSTNAME:-}"
        with_network="${WITH_NETWORK:-0}"
        network_name="${NETWORK_NAME:-}"
        if [[ "${WITH_TTYD_AUTH:-0}" == "1" ]] && (( ! with_ttyd_auth )); then
            orcan_die "last start used --web-terminal-auth; pass it again: orcan up --resume --web-terminal-auth USER:PASS"
        fi
        (( with_ttyd_auth )) || with_ttyd="${WITH_TTYD:-0}"
    fi

    if (( with_docker && with_network )); then
        orcan_usage_error "--docker-socket and --network are mutually exclusive (pick socket control or network reachability, not both)"
    fi
    if (( with_ttyd_opt && with_ttyd_auth )); then
        orcan_usage_error "--web-terminal and --web-terminal-auth are mutually exclusive (pick browser without a password, or browser with USER:PASS, not both)"
    fi
    if (( with_ttyd_auth )); then
        if [[ "${ttyd_credential}" != *:* ]]; then
            orcan_usage_error "--web-terminal-auth must be in USER:PASS format"
        fi
        local auth_user auth_pass
        auth_user="${ttyd_credential%%:*}"
        auth_pass="${ttyd_credential#*:}"
        if [[ -z "${auth_user}" || -z "${auth_pass}" ]]; then
            orcan_usage_error "--web-terminal-auth must have non-empty USER and PASS"
        fi
    fi

    if [[ -n "$github_hostname" ]] && ((!with_github)); then
        orcan_usage_error '--github-hostname requires --github'
    fi
    if ((with_github)); then
        github_hostname="${github_hostname:-github.com}"
        github_hostname="${github_hostname,,}"
        [[ ${#github_hostname} -le 253 && "$github_hostname" =~ ^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)*[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]] || orcan_usage_error '--github-hostname requires a hostname without a URL, path or port'
    fi

    orcan_require_docker
    orcan_require_generated
    orcan_load_env
    orcan_maybe_hint_upgrade

    local git_overlay=""
    if ((with_github)); then
        orcan_prepare_github "${github_hostname}" || return
    fi

    if (( with_git )); then
        git_overlay="$(orcan_write_git_overlay)"
    fi

    if (( with_docker )); then
        orcan_warn "SECURITY: --docker-socket mounts the host Docker socket into the container."
        orcan_warn "  Agents/tools inside can control the host Docker engine (full host reach)."
    fi
    if (( with_git )); then
        orcan_warn "SECURITY: --ssh mounts host ~/.ssh (and SSH agent if set) into the container."
        orcan_warn "  Agents/tools inside can use those keys for git push and other SSH access."
    fi
    if ((with_github)); then
        orcan_warn "GitHub token for ${github_hostname} is available to agents and Docker administrators."
    fi
    if ((with_docker || with_git || with_github)); then
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
    if ((with_github)); then
        label="${label}, GitHub ${github_hostname} enabled"
    fi
    if (( with_network )); then
        label="${label}, network '${network_name}' joined"
    fi
    if (( with_ttyd_auth )); then
        label="${label}, ttyd auth enabled"
    fi

    if (( with_docker )); then
        if [[ ! -S /var/run/docker.sock ]]; then
            orcan_die "/var/run/docker.sock not found"
        fi
    fi

    orcan_info "starting container (${label})"
    if (( with_ttyd_auth )); then
        export TTYD_CREDENTIAL="${ttyd_credential}"
    fi
    orcan_compose_up_run "${with_docker}" "${with_git}" "${with_network}" "${with_ttyd}" "${with_github}" up -d
    orcan_write_up_state "${with_docker}" "${with_git}" "${with_network}" "${with_ttyd}" "${network_name}" "${with_github}" "${github_hostname}"
    orcan_write_last_up "${with_docker}" "${with_git}" "${with_network}" "${with_ttyd}" "${with_ttyd_auth}" "${network_name}" "${with_github}" "${github_hostname}"

    if (( with_docker )); then
        if ! orcan_compose_up_run "${with_docker}" "${with_git}" "${with_network}" "${with_ttyd}" "${with_github}" exec -T orcan test -S /var/run/docker.sock 2> /dev/null; then
            orcan_warn "Docker socket missing in container; recreating…"
            orcan_compose_up_run "${with_docker}" "${with_git}" "${with_network}" "${with_ttyd}" "${with_github}" up -d --force-recreate
            if ! orcan_compose_up_run "${with_docker}" "${with_git}" "${with_network}" "${with_ttyd}" "${with_github}" exec -T orcan test -S /var/run/docker.sock 2> /dev/null; then
                orcan_die "/var/run/docker.sock is not mounted in the container"
            fi
        fi
    fi

    if (( with_git )); then
        if ! orcan_compose_up_run "${with_docker}" "${with_git}" "${with_network}" "${with_ttyd}" "${with_github}" exec -T orcan test -d /home/developer/.ssh 2> /dev/null &&
            ! orcan_compose_up_run "${with_docker}" "${with_git}" "${with_network}" "${with_ttyd}" "${with_github}" exec -T orcan test -S /run/host-ssh-agent.sock 2> /dev/null; then
            orcan_warn "git/SSH mounts missing in container; recreating…"
            orcan_compose_up_run "${with_docker}" "${with_git}" "${with_network}" "${with_ttyd}" "${with_github}" up -d --force-recreate
        fi
    fi

    if (( with_network )); then
        local container_name
        container_name="$(orcan_container_name)"
        if ! docker network inspect "${network_name}" --format '{{range .Containers}}{{.Name}} {{end}}' 2> /dev/null |
            grep -qw "${container_name}"; then
            orcan_warn "network '${network_name}' not attached; recreating…"
            orcan_compose_up_run "${with_docker}" "${with_git}" "${with_network}" "${with_ttyd}" "${with_github}" up -d --force-recreate
            if ! docker network inspect "${network_name}" --format '{{range .Containers}}{{.Name}} {{end}}' 2> /dev/null |
                grep -qw "${container_name}"; then
                orcan_die "container is not attached to network '${network_name}'"
            fi
        fi
    fi

    printf '\n'
    if (( with_ttyd )); then
        orcan_ok "browser terminal ready — open $(orcan_terminal_url)"
        printf '  Launcher → workspace → tmux\n'
        if (( with_ttyd_auth )); then
            printf '  ttyd auth: enabled (user: %s)\n' "${ttyd_credential%%:*}"
        fi
    else
        orcan_ok "container ready — local access: orcan enter"
        printf '  Remote browser terminal: orcan up --web-terminal\n'
    fi
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
    if (( with_network )); then
        printf '  Docker network: %s\n' "${network_name}"
    fi
    printf '\nStop with: orcan down\n'
    if (( ! with_ttyd )); then
        printf 'Need a browser terminal?  orcan down && orcan up --web-terminal\n'
    fi
    if (( ! with_git )); then
        printf 'Need git push/pull over SSH?  orcan up --ssh\n'
    fi
    if (( ! with_docker && ! with_network )); then
        printf 'Need Docker socket OR network reachability (pick one, not both)?\n'
        printf '  orcan up --docker-socket          # control host Docker engine\n'
        printf '  orcan up --network NAME    # join an existing network only\n'
    elif (( ! with_docker )); then
        printf 'Need Docker-in-Docker?  orcan up --docker-socket   (cannot combine with --network)\n'
    elif (( ! with_network )); then
        printf 'Need to reach containers on an existing Docker network?  orcan up --network NAME   (cannot combine with --docker-socket)\n'
    fi
}
