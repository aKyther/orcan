#!/usr/bin/env bash
# Git helpers for orcan update + soft update hints.
# shellcheck shell=bash

# Latest SemVer release tag locally (vX.Y.Z only — no -rc / -beta).
orcan_git_latest_release_tag() {
    git -C "${ORCAN_ROOT}" tag -l 'v*' --sort=-v:refname \
        | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' \
        | head -1
}

# What this install currently is (tag, or v$VERSION from file).
orcan_git_local_release_tag() {
    local tag ver
    if [[ -d "${ORCAN_ROOT}/.git" ]]; then
        tag="$(git -C "${ORCAN_ROOT}" describe --tags --exact-match 2>/dev/null || true)"
        if [[ "${tag}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            printf '%s\n' "${tag}"
            return 0
        fi
    fi
    ver="$(tr -d '[:space:]' < "${ORCAN_ROOT}/VERSION" 2>/dev/null || true)"
    if [[ "${ver}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        printf 'v%s\n' "${ver}"
        return 0
    fi
    return 1
}

# Newest vX.Y.Z on origin (network). Empty on failure.
orcan_git_remote_latest_release_tag() {
    local out
    if ! command -v git >/dev/null 2>&1; then
        return 1
    fi
    if [[ ! -d "${ORCAN_ROOT}/.git" ]]; then
        return 1
    fi
    if command -v timeout >/dev/null 2>&1; then
        out="$(timeout 4 git -C "${ORCAN_ROOT}" ls-remote --tags --refs origin 'v*' 2>/dev/null || true)"
    else
        out="$(git -C "${ORCAN_ROOT}" ls-remote --tags --refs origin 'v*' 2>/dev/null || true)"
    fi
    [[ -n "${out}" ]] || return 1
    printf '%s\n' "${out}" \
        | awk '{print $2}' \
        | sed 's#refs/tags/##' \
        | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' \
        | sort -V \
        | tail -1
}

# True if $2 is a newer SemVer tag than $1 (both vX.Y.Z).
orcan_git_tag_newer() {
    local a="$1" b="$2" newest
    [[ -n "${a}" && -n "${b}" ]] || return 1
    [[ "${a}" == "${b}" ]] && return 1
    newest="$(printf '%s\n%s\n' "${a}" "${b}" | sort -V | tail -1)"
    [[ "${newest}" == "${b}" ]]
}

# Soft check used by orcan up (and similar). Never fails the command.
# Skip: ORCAN_NO_UPDATE_CHECK=1
# Force: ORCAN_UPDATE_CHECK=1 (ignore cache)
# Cache TTL hours: ORCAN_UPDATE_CHECK_HOURS (default 12)
orcan_maybe_hint_update() {
    local cache_dir cache_file now ttl last local_tag remote_tag

    if [[ -n "${ORCAN_NO_UPDATE_CHECK:-}" ]]; then
        return 0
    fi
    if ! command -v git >/dev/null 2>&1; then
        return 0
    fi
    if [[ ! -d "${ORCAN_ROOT}/.git" ]]; then
        return 0
    fi

    cache_dir="${ORCAN_DATA:-${XDG_CONFIG_HOME:-${HOME}/.config}/orcan}/cache"
    cache_file="${cache_dir}/update-check"
    mkdir -p "${cache_dir}" 2>/dev/null || true
    now="$(date +%s 2>/dev/null || echo 0)"
    ttl=$(( ${ORCAN_UPDATE_CHECK_HOURS:-12} * 3600 ))

    if [[ -z "${ORCAN_UPDATE_CHECK:-}" && -f "${cache_file}" ]]; then
        last="$(awk -F= '/^checked_at=/{print $2}' "${cache_file}" 2>/dev/null || true)"
        if [[ -n "${last}" && "${now}" -gt 0 && $((now - last)) -lt ${ttl} ]]; then
            remote_tag="$(awk -F= '/^remote=/{print $2}' "${cache_file}" 2>/dev/null || true)"
            local_tag="$(awk -F= '/^local=/{print $2}' "${cache_file}" 2>/dev/null || true)"
            if [[ -n "${remote_tag}" && -n "${local_tag}" ]] \
                && orcan_git_tag_newer "${local_tag}" "${remote_tag}"; then
                orcan_warn "update available: ${remote_tag} (you have ${local_tag}) — run: orcan update"
            fi
            return 0
        fi
    fi

    local_tag="$(orcan_git_local_release_tag 2>/dev/null || true)"
    remote_tag="$(orcan_git_remote_latest_release_tag 2>/dev/null || true)"

    if [[ -n "${local_tag}" || -n "${remote_tag}" ]]; then
        printf 'checked_at=%s\nlocal=%s\nremote=%s\n' \
            "${now}" "${local_tag}" "${remote_tag}" > "${cache_file}" 2>/dev/null || true
    fi

    if [[ -z "${local_tag}" || -z "${remote_tag}" ]]; then
        return 0
    fi
    if orcan_git_tag_newer "${local_tag}" "${remote_tag}"; then
        orcan_warn "update available: ${remote_tag} (you have ${local_tag}) — run: orcan update"
    fi
}

orcan_git_update() {
    local channel="${1:-release}"
    local tag current

    orcan_require_git
    if [[ ! -d "${ORCAN_ROOT}/.git" ]]; then
        orcan_die "ORCAN_ROOT is not a git checkout: ${ORCAN_ROOT}"
    fi

    (
        cd "${ORCAN_ROOT}"
        orcan_info "fetching origin (tags + branches)…"
        git fetch --tags --prune origin

        if [[ "${channel}" == "main" ]]; then
            orcan_info "channel=main — fast-forward origin/main"
            git checkout main 2>/dev/null || git checkout -B main origin/main
            git pull --ff-only origin main
            current="$(git rev-parse --short HEAD)"
            orcan_ok "on main @ ${current}"
            return 0
        fi

        tag="$(orcan_git_latest_release_tag || true)"
        if [[ -z "${tag}" ]]; then
            orcan_die "no release tags (vX.Y.Z) found — try: orcan update --main"
        fi

        current="$(git describe --tags --exact-match 2>/dev/null || true)"
        if [[ "${current}" == "${tag}" ]]; then
            orcan_ok "already on latest release ${tag}"
            return 0
        fi

        orcan_info "checking out latest release ${tag}"
        git checkout --detach "${tag}"
        orcan_ok "now on ${tag} ($(git rev-parse --short HEAD))"
    )
    # Refresh soft-check cache so orcan up does not keep hinting.
    rm -f "${ORCAN_DATA:-${XDG_CONFIG_HOME:-${HOME}/.config}/orcan}/cache/update-check" 2>/dev/null || true
}
