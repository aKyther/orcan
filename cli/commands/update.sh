#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_update() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h | --help)
                cat <<'EOF'
usage: orcan update

  Dev channel: fast-forward this checkout to origin/main.

  For releases instead: orcan upgrade (newest) / orcan downgrade (previous)
  / orcan upgrade --to VERSION (pin a specific release, up or down).

  Does not rebuild the image — run orcan build if Dockerfile/rootfs changed.
EOF
                return 0
                ;;
            *)
                orcan_usage_error "unknown argument: $1"
                ;;
        esac
    done

    orcan_git_update
    orcan_ok "update complete"
    orcan_info "run: orcan doctor && orcan sync   # if config schema changed"
    orcan_info "run: orcan build                  # if Dockerfile/rootfs changed"
}
