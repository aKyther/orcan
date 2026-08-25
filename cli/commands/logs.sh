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
        context-scan | scan)
            docker exec -u developer "${cname}" \
                bash -lc 'f=~/.local/share/orcan/history/supervisor/childlog/context-scan.out.log; if [[ -f $f ]]; then tail -n 80 "$f"; else echo "no context-scan log yet"; fi'
            ;;
        -h | --help)
            printf 'usage: orcan logs [docker|supervisor|context-scan]\n'
            printf '  (default) docker          follow container stdout (docker logs -f)\n'
            printf '  supervisor                supervisord status + recent durable logs\n'
            printf '  context-scan              last lines of Reflection scanner stdout\n'
            ;;
        *)
            orcan_usage_error "unknown logs target: ${target} (try: docker|supervisor|context-scan)"
            ;;
    esac
}
