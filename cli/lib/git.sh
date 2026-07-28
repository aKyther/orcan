#!/usr/bin/env bash
# Git helpers for orcan update.
# shellcheck shell=bash

orcan_git_update() {
    local branch
    orcan_require_git
    if [[ ! -d "${ORCAN_ROOT}/.git" ]]; then
        orcan_die "ORCAN_ROOT is not a git checkout: ${ORCAN_ROOT}"
    fi
    (
        cd "${ORCAN_ROOT}"
        branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
        orcan_info "updating ${ORCAN_ROOT} (branch: ${branch:-detached})"
        git fetch --tags --prune
        if [[ -n "${branch}" && "${branch}" != "HEAD" ]]; then
            git pull --ff-only origin "${branch}"
        else
            orcan_warn "detached HEAD — fetched tags only; checkout a branch to pull"
        fi
    )
}
