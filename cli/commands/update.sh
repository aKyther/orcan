#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_update() {
    local channel="release"
    local target=""
    local channel_set=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --main)
                if (( channel_set )); then
                    orcan_usage_error "use only one of --release / --main / --to"
                fi
                channel="main"
                channel_set=1
                shift
                ;;
            --release)
                if (( channel_set )); then
                    orcan_usage_error "use only one of --release / --main / --to"
                fi
                channel="release"
                channel_set=1
                shift
                ;;
            --to)
                if (( channel_set )); then
                    orcan_usage_error "use only one of --release / --main / --to"
                fi
                shift
                [[ $# -gt 0 ]] || orcan_usage_error "--to needs a version (vX.Y.Z)"
                channel="to"
                target="$1"
                channel_set=1
                shift
                ;;
            -h | --help)
                cat <<'EOF'
usage: orcan update [--release|--main|--to VERSION]

  Default (--release): checkout the newest SemVer tag vX.Y.Z (GitHub Release).
  --main:              follow origin/main (maintainers / bleeding edge).
  --to VERSION:        checkout a specific release (vX.Y.Z or X.Y.Z).

  To go one release back after a bad update: orcan downgrade
  (or: orcan downgrade --to VERSION).

  Does not rebuild the image — run orcan build if Dockerfile/rootfs changed.
EOF
                return 0
                ;;
            *)
                orcan_usage_error "unknown argument: $1"
                ;;
        esac
    done

    orcan_git_update "${channel}" "${target}"
    orcan_ok "update complete"
    orcan_info "run: orcan doctor && orcan sync   # if config schema changed"
    orcan_info "run: orcan build                  # if Dockerfile/rootfs changed"
}
