#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_build() {
    local agents=""
    local profile_config=""
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
            --config)
                [[ $# -ge 2 && -f "$2" ]] || orcan_usage_error '--config requires an existing JSON file'
                profile_config="$2"
                shift 2
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
  list Go/Rust source images; [] omits both. CLI flags override agent selection.
  --config FILE: read the build section from a specific JSON file.

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
    cfg="${profile_config}"
    if [[ -z "${cfg}" ]]; then cfg="$(orcan_config_path)" || cfg=""; fi
    profile="$(orcan_host_python "${ORCAN_SCRIPTS}/image-profile.py" --config "${cfg}" --agents "${agents}")" || return
    if (( plan )); then
        printf '%s\n' "${profile}"
        return 0
    fi
    values="$(python3 -c 'import json,sys; p=json.load(sys.stdin); t={v["name"]:v["image"] for v in p["tools"]}; print("+".join(v["name"] for v in p["agents"])); print(int("go" in t)); print(int("rust" in t)); print(t.get("go","golang:1.27-bookworm")); print(t.get("rust","rust:1-bookworm"))' <<<"${profile}")"
    local -a selection
    mapfile -t selection <<<"${values}"
    agents="${selection[0]}"


    orcan_require_docker
    orcan_require_env_for_build
    orcan_load_env
    orcan_runtime_warn_if_config_stale build

    local INSTALL_GO="${selection[1]}" INSTALL_RUST="${selection[2]}"
    local GO_IMAGE="${selection[3]}" RUST_IMAGE="${selection[4]}" ORCAN_BUILD_PROFILE_JSON="${profile}"
    export INSTALL_GO INSTALL_RUST GO_IMAGE RUST_IMAGE ORCAN_BUILD_PROFILE_JSON
    orcan_image_build_local "${agents}" "${no_cache}" "${prune}" "${remove_previous}"
}
