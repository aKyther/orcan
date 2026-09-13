#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_build() {
    local agents=""
    local no_cache=0
    local prune=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --agent)
                [[ -n "${2:-}" ]] || orcan_usage_error "--agent needs: cursor|claude|codex|gemini|copilot"
                case "${2}" in cursor|claude|codex|gemini|copilot) ;; *) orcan_usage_error "unknown agent: ${2}";; esac
                if [[ "+${agents}+" != *"+$2+"* ]]; then
                    agents="${agents:+${agents}+}$2"
                fi
                shift 2
                ;;
            --all-agents)
                agents="cursor+claude+codex+gemini+copilot"
                shift
                ;;
            --no-cache)
                no_cache=1
                shift
                ;;
            --prune)
                prune=1
                shift
                ;;
            --force | --no-pull)
                shift
                ;;
            --no-publish)
                orcan_warn "--no-publish is obsolete (build never publishes; use: orcan publish)"
                shift
                ;;
            -h | --help)
                cat <<'EOF'
usage: orcan build --agent NAME [--agent NAME ...] | --all-agents [--no-cache|--force] [--prune]

  NAME: cursor | claude | codex | gemini | copilot
  Builds the standard orcan:latest image. Its /etc/orcan/agents.json records
  the selected CLIs. Build selection is explicit; use --all-agents for all.
  --prune removes dangling Orcan images after a successful build. It never
  runs docker system prune or removes BuildKit cache.
EOF
                return 0
                ;;
            *)
                orcan_usage_error "unknown argument: $1"
                ;;
        esac
    done

    [[ -n "${agents}" ]] || orcan_usage_error "choose at least one agent: orcan build --agent codex (or --all-agents)"

    orcan_require_docker
    orcan_require_env_for_build
    orcan_load_env
    orcan_runtime_warn_if_config_stale build

    orcan_image_build_local "${agents}" "${no_cache}" "${prune}"
}
