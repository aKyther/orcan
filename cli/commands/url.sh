#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_url() {
    orcan_require_generated
    orcan_load_env
    printf 'http://localhost:%s\n' "${TTYD_HOST_PORT:-7681}"
}
