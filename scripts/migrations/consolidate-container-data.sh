#!/usr/bin/env bash
# Migration: consolidate host $ORCAN_DATA for the flatter container home.
# See CHANGELOG.md [Unreleased] and scripts/migrations/README.md.
#
# Run on the HOST before the first `orcan sync` / `orcan up` with the new code.
# Safe to re-run: never overwrites non-empty destinations; never deletes.
#
# Older layouts handled:
#   A) flat:   $ORCAN_DATA/{npm,pnpm,cargo,go,shell-history,cache}
#   B) nested: $ORCAN_DATA/cache/{cache,npm,pnpm,cargo,go} + shell-history
# Target:
#   $ORCAN_DATA/cache/   → container ~/.cache
#   $ORCAN_DATA/history/ → container ~/.local/share/orcan/history

set -Eeuo pipefail

DATA="${ORCAN_DATA:-${XDG_CONFIG_HOME:-${HOME}/.config}/orcan}"

info() { printf '%s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
skip() { printf 'skip: %s\n' "$*"; }

dir_nonempty() {
    [[ -d "$1" ]] && [[ -n "$(ls -A "$1" 2>/dev/null || true)" ]]
}

move_dir_if_dst_empty() {
    local src="$1" dst="$2"
    if [[ ! -d "${src}" ]]; then
        skip "no ${src}"
        return 0
    fi
    if dir_nonempty "${dst}"; then
        warn "destination not empty — merge by hand: ${src}  ->  ${dst}"
        return 0
    fi
    mkdir -p "$(dirname "${dst}")"
    [[ -d "${dst}" ]] && rmdir "${dst}" 2>/dev/null || true
    mv -v "${src}" "${dst}"
}

move_into_cache() {
    local src="$1" name="$2"
    local dst="${DATA}/cache/${name}"
    [[ -d "${src}" ]] || return 0
    if dir_nonempty "${dst}"; then
        warn "destination not empty — merge by hand: ${src}  ->  ${dst}"
        return 0
    fi
    mkdir -p "${DATA}/cache"
    [[ -d "${dst}" ]] && rmdir "${dst}" 2>/dev/null || true
    mv -v "${src}" "${dst}"
}

if [[ ! -d "${DATA}" ]]; then
    info "nothing to migrate (no ${DATA}) — fresh install"
    exit 0
fi

info "Consolidating container data under ${DATA}"
info ""

# --- history ---
move_dir_if_dst_empty "${DATA}/shell-history" "${DATA}/history"
move_dir_if_dst_empty "${DATA}/bash-history" "${DATA}/history"

# --- nested cache/cache: promote XDG payload + tool siblings into one cache/ ---
if [[ -d "${DATA}/cache/cache" ]]; then
    info "flattening nested ${DATA}/cache/cache"
    staging="$(mktemp -d "${TMPDIR:-/tmp}/orcan-cache-migrate.XXXXXX")"
    if dir_nonempty "${DATA}/cache/cache"; then
        # shellcheck disable=SC2035
        shopt -s dotglob nullglob
        for f in "${DATA}/cache/cache"/*; do
            base="$(basename "${f}")"
            if [[ -e "${staging}/${base}" ]]; then
                warn "skip overlap in staging: ${base}"
            else
                mv -v "${f}" "${staging}/${base}"
            fi
        done
        shopt -u dotglob nullglob
    fi
    rmdir "${DATA}/cache/cache" 2>/dev/null || warn "could not remove ${DATA}/cache/cache"

    for tool in npm pnpm cargo go; do
        if [[ -d "${DATA}/cache/${tool}" ]]; then
            if [[ -e "${staging}/${tool}" ]]; then
                warn "skip overlap: cache/${tool}"
            else
                mv -v "${DATA}/cache/${tool}" "${staging}/${tool}"
            fi
        fi
    done

    # Move any other leftover entries under cache/ into staging
    shopt -s nullglob
    for f in "${DATA}/cache"/*; do
        base="$(basename "${f}")"
        if [[ -e "${staging}/${base}" ]]; then
            warn "skip leftover overlap: ${f}"
            continue
        fi
        mv -v "${f}" "${staging}/${base}"
    done
    shopt -u nullglob

    if dir_nonempty "${DATA}/cache"; then
        warn "${DATA}/cache still has leftovers — staging left at ${staging}"
    else
        rmdir "${DATA}/cache" 2>/dev/null || true
        mv -v "${staging}" "${DATA}/cache"
    fi
fi

# --- flat siblings next to cache/ ---
mkdir -p "${DATA}/cache"
for tool in npm pnpm cargo go; do
    move_into_cache "${DATA}/${tool}" "${tool}"
done

info ""
info "Done. Next:"
info "  orcan sync"
info "  orcan down && orcan up"
info "Optional: remove empty leftovers under ${DATA} after confirming history/cache."
