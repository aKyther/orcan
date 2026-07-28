#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_update() {
    local channel="release"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --main)
                channel="main"
                shift
                ;;
            --release)
                channel="release"
                shift
                ;;
            -h | --help)
                cat <<'EOF'
usage: orcan update [--release|--main]

  Default (--release): checkout the newest SemVer tag vX.Y.Z (GitHub Release).
  --main:              follow origin/main (maintainers / bleeding edge).

  Does not rebuild the image — run orcan build if Dockerfile/rootfs changed.
EOF
                return 0
                ;;
            *)
                orcan_usage_error "unknown argument: $1"
                ;;
        esac
    done

    orcan_git_update "${channel}"
    orcan_ok "update complete"
    orcan_info "run: orcan doctor && orcan sync   # if config schema changed"
    orcan_info "run: orcan build                  # if Dockerfile/rootfs changed"
}
