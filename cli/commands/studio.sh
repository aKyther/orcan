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
                    --image "${IMAGE_LOCAL:-orcan:latest}" \
                    --container "orcan-${ORCAN_INSTANCE:-1}"
            ;;
        -h | --help | "")
            printf 'usage: orcan studio probe --json\n'
            printf '  Read-only, versioned Sandbox capability report for Orcan Studio.\n'
            ;;
        *)
            orcan_usage_error 'usage: orcan studio probe --json'
            ;;
    esac
}
