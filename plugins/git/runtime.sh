#!/usr/bin/env bash
# shellcheck shell=bash


# Identity is resolved from the host Git configuration by runtime-settings.py.
# Repository-local identities remain authoritative inside the container.

orcan_plugin_git_prepare() {
    local identity
    identity="$(orcan_host_python "${ORCAN_ROOT}/plugins/git/identity.py")" || return
    eval "${identity}"
}
