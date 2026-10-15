#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_actions() {
    "${ORCAN_ROOT}/docker/rootfs/usr/local/bin/orcan-actions" "$@"
}
