#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_upgrade() {
    local channel="release"
    local target=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --to)
                shift
                [[ $# -gt 0 ]] || orcan_usage_error "--to needs a version (vX.Y.Z)"
                channel="to"
                target="$1"
                shift
                ;;
            -h | --help)
                cat <<'EOF'
usage: orcan upgrade [--to VERSION]

  Default: checkout the newest SemVer release tag vX.Y.Z (GitHub Release).
  --to VERSION: checkout a specific release (vX.Y.Z or X.Y.Z; up or down).

  For the dev channel instead: orcan update (fast-forward origin/main)
  To go one release back: orcan downgrade

  Does not rebuild the image — run orcan build if Dockerfile/rootfs changed.
EOF
                return 0
                ;;
            *)
                orcan_usage_error "unknown argument: $1"
                ;;
        esac
    done

    orcan_git_upgrade "${channel}" "${target}"
    orcan_ok "upgrade complete"
    orcan_info "run: orcan doctor && orcan sync   # if config schema changed"
    orcan_info "run: orcan build                  # if Dockerfile/rootfs changed"
}
