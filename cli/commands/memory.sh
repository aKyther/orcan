#!/usr/bin/env bash
# shellcheck shell=bash
orcan_cmd_memory() {
    python3 "${ORCAN_ROOT}/docker/rootfs/usr/local/bin/orcan-memory" "$@"
}
