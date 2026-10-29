#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_build() {
    local agents=""
    local plan=0
    local no_cache=0
    local prune=0
    local remove_previous=0
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
            --plan)
                plan=1
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
            --remove-previous)
                remove_previous=1
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
usage: orcan build [--plan] [--agent NAME ... | --all-agents] [--no-cache|--force] [--prune] [--remove-previous]

  --plan: print the resolved JSON profile without building or requiring Docker.
  No --agent flag: use build.agents from orcan.config.json. build.tools can
  disable Go/Rust (defaults stay enabled); CLI agent flags override the profile.

  NAME: cursor | claude | codex | gemini | copilot
  Builds the standard orcan:latest image. Its /etc/orcan/agents.json records
  the selected CLIs. Build selection is explicit; use --all-agents for all.
  --prune removes dangling Orcan images after a successful build. It never
  runs docker system prune or removes BuildKit cache.
  --remove-previous asks [y/n] before removing old local orcan tags after a
  successful build. Images used by containers are kept; no forced removal.
EOF
                return 0
                ;;
            *)
                orcan_usage_error "unknown argument: $1"
                ;;
        esac
    done

    local cfg="" profile values
    cfg="$(orcan_config_path)" || cfg=""
    profile="$(orcan_host_python "${ORCAN_SCRIPTS}/image-profile.py" --config "${cfg}" --agents "${agents}")" || return
    if (( plan )); then
        printf '%s\n' "${profile}"
        return 0
    fi
    values="$(python3 -c 'import json,sys; p=json.load(sys.stdin); print("+".join(p["agents"])); print(int(p["tools"]["go"])); print(int(p["tools"]["rust"]))' <<<"${profile}")"
    local -a selection
    mapfile -t selection <<<"${values}"
    agents="${selection[0]}"


    orcan_require_docker
    orcan_require_env_for_build
    orcan_load_env
    orcan_runtime_warn_if_config_stale build

    local INSTALL_GO="${selection[1]}" INSTALL_RUST="${selection[2]}"
    export INSTALL_GO INSTALL_RUST
    orcan_image_build_local "${agents}" "${no_cache}" "${prune}" "${remove_previous}"
}
