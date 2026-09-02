#!/usr/bin/env bash
# Migration: old ~/.config/orcan/home/... layout -> new flat
# ~/.config/orcan/... layout. See CHANGELOG.md [Unreleased]
# "Breaking: flattened ~/.config/orcan/" and scripts/migrations/README.md.
#
# Run this on the HOST (not inside the orcan container), BEFORE the first
# `orcan sync` / `orcan build` / `orcan down && orcan up` with the new code.
# Safe to re-run: every step only moves a path if the source exists and the
# destination does not already have real content — never overwrites.

set -Eeuo pipefail

DATA="${ORCAN_DATA:-${XDG_CONFIG_HOME:-${HOME}/.config}/orcan}"
OLD_HOME="${DATA}/home"
NEW_HOME="${DATA}"

info()  { printf '%s\n' "$*"; }
warn()  { printf 'WARN: %s\n' "$*" >&2; }
skip()  { printf 'skip: %s\n' "$*"; }

move_file() {
    local src="$1" dst="$2"
    if [[ ! -f "${src}" ]]; then
        skip "no ${src}"
        return 0
    fi
    if [[ -f "${dst}" ]]; then
        warn "both exist, leaving old in place — resolve by hand: ${src}  vs  ${dst}"
        return 0
    fi
    mkdir -p "$(dirname "${dst}")"
    mv -v "${src}" "${dst}"
}

move_dir_if_dst_empty() {
    local src="$1" dst="$2"
    if [[ ! -d "${src}" ]]; then
        skip "no ${src}"
        return 0
    fi
    if [[ -d "${dst}" ]] && [[ -n "$(ls -A "${dst}" 2>/dev/null)" ]]; then
        warn "destination not empty, leaving old in place — merge by hand: ${src}  ->  ${dst}"
        return 0
    fi
    mkdir -p "$(dirname "${dst}")"
    if [[ -d "${dst}" ]]; then
        rmdir "${dst}"
    fi
    mv -v "${src}" "${dst}"
}

if [[ ! -d "${OLD_HOME}" ]]; then
    info "nothing to migrate (no ${OLD_HOME}) — already on the new layout, or a fresh install"
    exit 0
fi

info "Migrating ${OLD_HOME} -> ${NEW_HOME}"
info ""

move_file "${OLD_HOME}/orcan.config.json" "${NEW_HOME}/orcan.config.json"
move_file "${OLD_HOME}/.env" "${NEW_HOME}/.env"
move_file "${OLD_HOME}/.env.example" "${NEW_HOME}/.env.example"

# The critical one: per-workspace meta (.claude/settings.json, session-brief,
# generated workspace state). Everything else under the old
# .orcan/ (compose-*.yml, runtime-config.json, workspace.manifest.json,
# context-tui-state.json, *.code-workspace) is purely derived/generated and
# will be rewritten correctly by the next `orcan sync` — safe to leave behind.
move_dir_if_dst_empty "${OLD_HOME}/.orcan/workspaces" "${NEW_HOME}/workspaces"

info ""
if [[ -d "${OLD_HOME}" ]]; then
    remaining="$(find "${OLD_HOME}" -mindepth 1 2>/dev/null | wc -l | tr -d ' ')"
    if [[ "${remaining}" == "0" ]]; then
        rmdir "${OLD_HOME}" 2>/dev/null || true
        info "removed now-empty ${OLD_HOME}"
    else
        info "${OLD_HOME} still has ${remaining} item(s) left (generated files/backups) — safe to leave or delete by hand"
    fi
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/../.." && pwd)"

info ""
info "Done. Next, using THIS checkout's launcher (not a possibly-different PATH orcan):"
info "  ${repo_root}/bin/orcan build"
info "  ${repo_root}/bin/orcan sync"
info "  ${repo_root}/bin/orcan down && ${repo_root}/bin/orcan up"
