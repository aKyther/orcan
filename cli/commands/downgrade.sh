#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_downgrade() {
    local target=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --to)
                shift
                [[ $# -gt 0 ]] || orcan_usage_error "--to needs a version (vX.Y.Z)"
                target="$1"
                shift
                ;;
            -h | --help)
                cat <<'EOF'
usage: orcan downgrade [--to VERSION]

  Default: checkout the previous SemVer release (one step older than current).
  --to VERSION: checkout that release (must not be newer than current).

  For any pin (up or down): orcan update --to VERSION

  Does not rebuild the image — run orcan build if Dockerfile/rootfs changed.
EOF
                return 0
                ;;
            *)
                orcan_usage_error "unknown argument: $1"
                ;;
        esac
    done

    orcan_git_downgrade "${target}"
    orcan_ok "downgrade complete"
    orcan_info "run: orcan doctor && orcan sync   # if config schema changed"
    orcan_info "run: orcan build                  # if Dockerfile/rootfs changed"
}
