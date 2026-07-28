#!/usr/bin/env bash
# shellcheck shell=bash
# Enter the running container from a local host terminal (alongside ttyd).

orcan_enter_compose() {
    if orcan_compose_ttyd_docker ps -q orcan 2>/dev/null | grep -q .; then
        orcan_compose_ttyd_docker "$@"
    elif orcan_compose_ttyd ps -q orcan 2>/dev/null | grep -q .; then
        orcan_compose_ttyd "$@"
    else
        orcan_die "no running container — start with: orcan up"
    fi
}

orcan_enter_exec() {
    local -a flags=(exec)
    if [[ -t 0 && -t 1 ]]; then
        flags+=(-it)
    else
        flags+=(-i)
    fi
    orcan_enter_compose "${flags[@]}" orcan "$@"
}

orcan_cmd_enter() {
    local mode="launcher"
    local session=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -s | --shell)
                mode="shell"
                shift
                ;;
            -l | --launcher)
                mode="launcher"
                shift
                ;;
            -t | --tmux)
                mode="tmux"
                session="${2:-}"
                if [[ -n "${session}" && "${session}" != -* ]]; then
                    shift 2
                else
                    shift
                    session=""
                fi
                ;;
            -h | --help)
                cat <<'EOF'
usage: orcan enter [--launcher|--shell|--tmux [SESSION]]

  Enter the running Orcan container from a local terminal (same stack as ttyd).

  (default) / --launcher   workspace picker (agent-launcher)
  --shell / -s             interactive zsh (not in tmux)
  --tmux / -t [SESSION]    attach tmux; omit SESSION to list / auto-attach if one

Also accepted: orcan go-in … (alias)

Examples:
  orcan enter
  orcan enter --shell
  orcan enter --tmux my-workspace
EOF
                return 0
                ;;
            *)
                orcan_usage_error "unknown argument: $1 (try: orcan enter --help)"
                ;;
        esac
    done

    orcan_require_docker

    case "${mode}" in
        shell)
            orcan_enter_exec zsh -l
            ;;
        launcher)
            orcan_enter_exec agent-launcher
            ;;
        tmux)
            if [[ -z "${session}" ]]; then
                local list count
                list="$(orcan_enter_compose exec -T orcan tmux ls 2>/dev/null || true)"
                if [[ -z "${list}" ]]; then
                    orcan_die "no tmux sessions — run: orcan enter   # picker creates one"
                fi
                count="$(printf '%s\n' "${list}" | grep -c . || true)"
                if [[ "${count}" -eq 1 ]]; then
                    session="${list%%:*}"
                    orcan_info "attaching to sole session: ${session}"
                else
                    printf '%s\n' "${list}"
                    orcan_die "pick a session: orcan enter --tmux NAME"
                fi
            fi
            orcan_enter_exec tmux attach -t "${session}"
            ;;
    esac
}

# Alias used by orcan.sh dispatch
orcan_cmd_go_in() {
    orcan_cmd_enter "$@"
}
