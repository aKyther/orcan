#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_compact() {
    python3 "${ORCAN_ROOT}/docker/rootfs/usr/local/lib/orcan/compact.py" "$@"
}
