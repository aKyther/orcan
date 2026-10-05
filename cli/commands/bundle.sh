#!/usr/bin/env bash
# Offline Orcan CLI kit creation. The kit intentionally excludes user state.

orcan_cmd_bundle() {
    local action="${1:-}" output="" image=""
    shift || true
    [[ "$action" == "create" ]] || orcan_usage_error "usage: orcan bundle create --output DIR [--image IMAGE]"
    while (($#)); do
        case "$1" in
            --output) output="${2:-}"; shift 2 ;;
            --image) image="${2:-}"; shift 2 ;;
            *) orcan_usage_error "unknown bundle option: $1" ;;
        esac
    done
    [[ -n "$output" ]] || orcan_usage_error "--output is required"
    local args=(--root "$ORCAN_ROOT" --output "$output")
    [[ -n "$image" ]] && args+=(--image "$image")
    orcan_host_python "$ORCAN_SCRIPTS/orcan-cli-kit.py" "${args[@]}"
}
