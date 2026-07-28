#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_update() {
    orcan_git_update
    orcan_ok "update complete"
    orcan_info "run: orcan doctor && orcan sync   # if config schema changed"
    orcan_info "run: orcan build                  # if Dockerfile/rootfs changed"
}
