#!/usr/bin/env bash
# shellcheck shell=bash

# Machine-readable Sandbox endpoints consumed by the separate Orcan Studio
# desktop application. Keep stdout JSON-only for the --json protocol.
orcan_cmd_studio() {
    local sub="${1:-}"
    shift || true

    case "${sub}" in
        instances)
            [[ "${1:-}" == "--json" && $# -eq 1 ]] || orcan_usage_error 'usage: orcan studio instances --json'
            orcan_require_python
            orcan_host_python "${ORCAN_SCRIPTS}/studio-instances.py" --root "${ORCAN_INSTANCES_ROOT:-${XDG_CONFIG_HOME:-${HOME}/.config}/orcan}"
            ;;
        probe)
            if [[ "${1:-}" != "--json" || $# -ne 1 ]]; then
                printf 'usage: orcan studio probe --json\n' >&2
                return 2
            fi
            orcan_require_python
            orcan_load_env
            local data="${ORCAN_DATA:-${XDG_CONFIG_HOME:-${HOME}/.config}/orcan}"
            local projects_root="${ORCAN_PROJECTS_ROOT:-${data}/sandbox}"
            local workspace_index="${ORCAN_WORKSPACE_INDEX:-${ORCAN_HOME}/workspaces/index.json}"
            if [[ -z "${ORCAN_NAMED_INSTANCE:-}" && ! -f "${workspace_index}" && -f "${HOME}/workspaces/index.json" ]]; then
                workspace_index="${HOME}/workspaces/index.json"
            fi
            ORCAN_STUDIO_DOCKER="${ORCAN_STUDIO_DOCKER:-docker}" \
                orcan_host_python "${ORCAN_SCRIPTS}/studio-probe.py" \
                    --protocol 1 \
                    --version "$(orcan_image_version)" \
                    --home "${ORCAN_HOME}" \
                    --data "${data}" \
                    --projects-root "${projects_root}" \
                    --workspace-index "${workspace_index}" \
                    --config "${ORCAN_CONFIG_FILE}" \
                    --runtime "${ORCAN_RUNTIME_DIR}/runtime-config.json" \
                    --last-up "$(orcan_last_up_file)" \
                    --image "${IMAGE_LOCAL:-orcan:latest}" \
                    --container "$(orcan_container_name)" \
                    --instance "${ORCAN_NAMED_INSTANCE:-}"
            ;;
        parent)
            local action="${1:-}"
            shift || true
            if [[ "${action}" != "plan" && "${action}" != "apply" ]]; then
                orcan_usage_error 'usage: orcan studio parent plan|apply --path PATH --branch BRANCH [--expected-head SHA --yes]'
                return
            fi
            orcan_require_python
            orcan_host_python "${ORCAN_SCRIPTS}/studio-parent.py" "${action}" "$@"
            ;;
        import)
            if [[ "${1:-}" != "plan" && "${1:-}" != "apply" ]]; then
                orcan_usage_error 'usage: orcan studio import plan|apply --source URL --projects-root PATH [--parent PATH] [--yes]'
                return
            fi
            shift
            orcan_require_python
            orcan_host_python "${ORCAN_SCRIPTS}/studio-import.py" "$@"
            ;;
        directory)
            if [[ "${1:-}" != "plan" && "${1:-}" != "apply" ]]; then
                orcan_usage_error 'usage: orcan studio directory plan|apply --projects-root PATH --parent PATH --name NAME [--yes]'
                return
            fi
            shift
            orcan_require_python
            orcan_host_python "${ORCAN_SCRIPTS}/studio-directory.py" "$@"
            ;;
        worktree)
            if [[ "${1:-}" != "list" && "${1:-}" != "branches" && "${1:-}" != "plan" && "${1:-}" != "apply" && "${1:-}" != "remove-plan" && "${1:-}" != "remove-apply" ]]; then orcan_usage_error 'usage: orcan studio worktree list|branches|plan|apply|remove-plan|remove-apply …'; return; fi
            shift; orcan_require_python
            orcan_host_python "${ORCAN_SCRIPTS}/studio-worktree.py" "$@"
            ;;
        settings)
            local mode="${1:-}"
            if [[ "${mode}" != "plan" && "${mode}" != "project-add-plan" && "${mode}" != "project-add-apply" && "${mode}" != "project-detach-plan" && "${mode}" != "project-detach-apply" && "${mode}" != "workspace-rename-plan" && "${mode}" != "workspace-rename-apply" && "${mode}" != "workspace-remove-plan" && "${mode}" != "workspace-remove-apply" ]]; then orcan_usage_error 'usage: orcan studio settings plan|project-add-plan|project-add-apply|project-detach-plan|project-detach-apply|workspace-rename-plan|workspace-rename-apply|workspace-remove-plan|workspace-remove-apply …'; return; fi
            shift; orcan_require_python
            # Orcan resolves its own config so Studio never guesses a path on the instance.
            orcan_host_python "${ORCAN_SCRIPTS}/studio-settings.py" "${mode}" --config "${ORCAN_CONFIG_FILE}" "$@"
            ;;
        enclave)
            local mode="${1:-}"; shift || true
            [[ "$mode" == "plan" || "$mode" == "apply" ]] || orcan_usage_error 'usage: orcan studio enclave plan|apply --empty [--with-git] [--with-docker] [--with-ttyd | --with-ttyd-auth USER:PASS] [--yes]'
            local up_args=() port_args=() apply_args=("$mode" --config "${ORCAN_CONFIG_FILE}")
            while (($#)); do
                case "$1" in
                    --empty) shift ;;
                    --ttyd-host-port)
                        [[ $# -ge 2 && "$2" =~ ^[0-9]+$ ]] || orcan_usage_error '--ttyd-host-port requires a port'
                        port_args+=(--ttyd-host-port "$2"); apply_args+=(--ttyd-host-port "$2"); shift 2 ;;
                    --cpus|--memory-gb)
                        [[ $# -ge 2 && "$2" != -* ]] || orcan_usage_error "$1 requires a value"
                        port_args+=("$1" "$2"); apply_args+=("$1" "$2"); shift 2 ;;
                    --with-git|--with-docker|--with-ttyd) up_args+=("$1"); shift ;;
                    --with-ttyd-auth)
                        [[ $# -ge 2 && "$2" != -* ]] || orcan_usage_error '--with-ttyd-auth requires user:password'
                        up_args+=("$1" "$2"); shift 2
                        ;;
                    --yes) apply_args+=(--yes); shift ;;
                    *) orcan_usage_error "unknown enclave option: $1" ;;
                esac
            done
            orcan_require_python
            if [[ "$mode" == "plan" ]]; then
                orcan_host_python "${ORCAN_SCRIPTS}/studio-enclave.py" "${apply_args[@]}"
                return
            fi
            # Studio consumes one JSON document on stdout. Runtime command
            # progress deliberately goes to stderr so it cannot corrupt that response.
            orcan_host_python "${ORCAN_SCRIPTS}/studio-enclave.py" "${apply_args[@]}" >/dev/null || return
            source "$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sync.sh"
            if ! ORCAN_STUDIO_CREATE_RUNTIME=1 orcan_cmd_sync >&2; then
                orcan_host_python "${ORCAN_SCRIPTS}/studio-enclave.py" rollback --config "${ORCAN_CONFIG_FILE}" "${port_args[@]}" --yes >&2 || true
                return 1
            fi
            source "$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)/up.sh"
            if ! orcan_cmd_up "${up_args[@]}" >&2; then
                orcan_host_python "${ORCAN_SCRIPTS}/studio-enclave.py" rollback --config "${ORCAN_CONFIG_FILE}" "${port_args[@]}" --yes >&2 || true
                return 1
            fi
            printf '%s\n' '{"ok":true,"result":{"operation":"empty_enclave"}}'
            ;;
        -h | --help | "")
            printf 'usage: orcan studio probe --json\n'
            printf '       orcan studio parent plan|apply --path PATH --branch BRANCH [--expected-head SHA --yes]\n'
            printf '       orcan studio directory plan|apply --projects-root PATH --parent PATH --name NAME [--yes]\n'
            printf '  Read-only, versioned Sandbox capability report for Orcan Studio.\n'
            ;;
        *)
            orcan_usage_error 'usage: orcan studio probe --json'
            ;;
    esac
}
