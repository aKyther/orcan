#!/usr/bin/env bash
# Migration: rename managed projects root space/ → sandbox/
# See CHANGELOG.md [Unreleased] and scripts/migrations/README.md.
#
# Old default: $ORCAN_DATA/space
# New default: $ORCAN_DATA/sandbox
#
# Run on the HOST. Safe to re-run. Never deletes; never overwrites non-empty dest.
# Rewrites ORCAN_PROJECTS_ROOT in .env and absolute path prefixes in configs.

set -Eeuo pipefail

DATA="${ORCAN_DATA:-${XDG_CONFIG_HOME:-${HOME}/.config}/orcan}"
OLD="${DATA}/space"
NEW="${DATA}/sandbox"

ENV_CANDIDATES=(
    "${ORCAN_HOME:-}/.env"
    "${DATA}/.env"
    "${HOME}/.config/orcan/.env"
)
CONFIG_CANDIDATES=(
    "${ORCAN_CONFIG:-}"
    "${ORCAN_HOME:-}/orcan.config.json"
    "${DATA}/orcan.config.json"
    "${HOME}/.config/orcan/orcan.config.json"
)

info() { printf '%s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }

dir_nonempty() {
    [[ -d "$1" ]] && [[ -n "$(ls -A "$1" 2>/dev/null || true)" ]]
}

rewrite_paths() {
    local file="$1" from="$2" to="$3"
    [[ -f "${file}" ]] || return 0
    grep -Fq "${from}" "${file}" 2>/dev/null || return 0
    local tmp
    tmp="$(mktemp)"
    if command -v python3 >/dev/null 2>&1; then
        python3 - "${file}" "${from}" "${to}" "${tmp}" <<'PY'
import sys
from pathlib import Path
path, old, new, out = sys.argv[1:5]
Path(out).write_text(Path(path).read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
PY
        mv -v "${tmp}" "${file}"
    else
        sed "s|${from}|${to}|g" "${file}" >"${tmp}"
        mv -v "${tmp}" "${file}"
    fi
    info "rewrote paths in ${file}"
}

if [[ ! -d "${OLD}" ]]; then
    info "nothing to migrate (no ${OLD}) — already on sandbox/, or fresh install"
    mkdir -p "${NEW}"
    exit 0
fi

if [[ "$(cd -- "${OLD}" && pwd -P)" == "$(mkdir -p "${NEW}" && cd -- "${NEW}" && pwd -P)" ]]; then
    info "old and new resolve to the same path — nothing to do"
    exit 0
fi

info "Renaming managed projects root:"
info "  from: ${OLD}"
info "  to:   ${NEW}"
info ""

if dir_nonempty "${NEW}"; then
    warn "destination not empty — leaving ${OLD} in place; merge by hand into ${NEW}"
    exit 1
fi

mkdir -p "$(dirname "${NEW}")"
[[ -d "${NEW}" ]] && rmdir "${NEW}" 2>/dev/null || true
mv -v "${OLD}" "${NEW}"

for envf in "${ENV_CANDIDATES[@]}"; do
    [[ -f "${envf}" ]] || continue
    rewrite_paths "${envf}" "${OLD}" "${NEW}"
done

for cfg in "${CONFIG_CANDIDATES[@]}"; do
    [[ -n "${cfg}" && -f "${cfg}" ]] || continue
    rewrite_paths "${cfg}" "${OLD}" "${NEW}"
done
if [[ -f "${NEW}/.worktrees/registry.json" ]]; then
    rewrite_paths "${NEW}/.worktrees/registry.json" "${OLD}" "${NEW}"
fi

info ""
info "Done. Next:"
info "  orcan sync"
info "  orcan down && orcan up   # projects-root bind path changed"
