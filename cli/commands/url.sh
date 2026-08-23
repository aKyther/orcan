#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_url() {
    orcan_require_generated
    orcan_load_env
    orcan_require_ttyd_for_url
    orcan_terminal_url
}
