#!/usr/bin/env bash
# shellcheck shell=bash
orcan_cmd_plugins() {
    case "${1:-list}" in
        help)
            ORCAN_PLUGIN_CATALOG="${ORCAN_ROOT}/plugins" python3 "${ORCAN_ROOT}/docker/rootfs/usr/local/bin/orcan-plugins" --help
            ;;
        --help|-h|list|validate)
            ORCAN_PLUGIN_CATALOG="${ORCAN_ROOT}/plugins" python3 "${ORCAN_ROOT}/docker/rootfs/usr/local/bin/orcan-plugins" "$@"
            ;;
        doctor)
            local container
            container="$(orcan_require_running_container)" || return
            docker exec -i "${container}" orcan-plugins "$@"
            ;;
        *) orcan_usage_error 'usage: orcan plugins list|validate|doctor [--plugin NAME]' ;;
    esac
}
