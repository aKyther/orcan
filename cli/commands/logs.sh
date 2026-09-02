#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_logs() {
    orcan_require_docker
    local cname
    cname="$(orcan_require_running_container)"

    local target="${1:-}"
    case "${target}" in
        "" | docker | container)
            docker logs -f "${cname}"
            ;;
        supervisor | supervisord)
            # Durable supervisor logs live on the history bind inside the container.
            docker exec -u developer "${cname}" \
                bash -lc 'orcan-supervisor-status 2>/dev/null || tail -n 80 ~/.local/share/orcan/history/supervisor/supervisord.log 2>/dev/null || echo "no supervisor logs yet — need orcan build + recreate"'
            ;;
        -h | --help)
            printf 'usage: orcan logs [docker|supervisor]\n'
            printf '  (default) docker          follow container stdout (docker logs -f)\n'
            printf '  supervisor                supervisord status + recent durable logs\n'
            ;;
        *)
            orcan_usage_error "unknown logs target: ${target} (try: docker|supervisor)"
            ;;
    esac
}
