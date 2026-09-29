#!/usr/bin/env bash
# shellcheck shell=bash

# Machine-readable Sandbox endpoints consumed by the separate Orcan Studio
# desktop application. Keep stdout JSON-only for the --json protocol.
orcan_cmd_studio() {
    local sub="${1:-}"
    shift || true

    case "${sub}" in
        probe)
            if [[ "${1:-}" != "--json" || $# -ne 1 ]]; then
                printf 'usage: orcan studio probe --json\n' >&2
                return 2
            fi
            orcan_require_python
            local data="${ORCAN_DATA:-${XDG_CONFIG_HOME:-${HOME}/.config}/orcan}"
            local projects_root="${ORCAN_PROJECTS_ROOT:-${data}/sandbox}"
            ORCAN_STUDIO_DOCKER="${ORCAN_STUDIO_DOCKER:-docker}" \
                orcan_host_python "${ORCAN_SCRIPTS}/studio-probe.py" \
                    --protocol 1 \
                    --version "$(orcan_image_version)" \
                    --home "${ORCAN_HOME}" \
                    --data "${data}" \
                    --projects-root "${projects_root}" \
                    --config "${ORCAN_CONFIG_FILE}" \
                    --runtime "${ORCAN_RUNTIME_DIR}/runtime-config.json" \
                    --last-up "$(orcan_last_up_file)" \
                    --image "${IMAGE_LOCAL:-orcan:latest}" \
                    --container "orcan-${ORCAN_INSTANCE:-1}"
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
                orcan_usage_error 'usage: orcan studio import plan|apply --source URL_OR_PATH --projects-root PATH [--destination PATH] [--yes]'
                return
            fi
            shift
            orcan_require_python
            orcan_host_python "${ORCAN_SCRIPTS}/studio-import.py" "$@"
            ;;
        worktree)
            if [[ "${1:-}" != "list" && "${1:-}" != "plan" && "${1:-}" != "apply" && "${1:-}" != "remove-plan" && "${1:-}" != "remove-apply" ]]; then orcan_usage_error 'usage: orcan studio worktree list|plan|apply|remove-plan|remove-apply …'; return; fi
            shift; orcan_require_python
            orcan_host_python "${ORCAN_SCRIPTS}/studio-worktree.py" "$@"
            ;;
        settings)
            local mode="${1:-}"
            if [[ "${mode}" != "plan" && "${mode}" != "project-add-plan" && "${mode}" != "project-add-apply" && "${mode}" != "project-detach-plan" && "${mode}" != "project-detach-apply" ]]; then orcan_usage_error 'usage: orcan studio settings plan|project-add-plan|project-add-apply|project-detach-plan|project-detach-apply …'; return; fi
            shift; orcan_require_python
            # Orcan resolves its own config so Studio never guesses a path on the instance.
            orcan_host_python "${ORCAN_SCRIPTS}/studio-settings.py" "${mode}" --config "${ORCAN_CONFIG_FILE}" "$@"
            ;;
        -h | --help | "")
            printf 'usage: orcan studio probe --json\n'
            printf '       orcan studio parent plan|apply --path PATH --branch BRANCH [--expected-head SHA --yes]\n'
            printf '  Read-only, versioned Sandbox capability report for Orcan Studio.\n'
            ;;
        *)
            orcan_usage_error 'usage: orcan studio probe --json'
            ;;
    esac
}
