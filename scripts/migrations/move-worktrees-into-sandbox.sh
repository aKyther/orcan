#!/usr/bin/env bash
# Migration: move managed git worktrees under ORCAN_PROJECTS_ROOT/.worktrees
# See CHANGELOG.md [Unreleased] and scripts/migrations/README.md.
#
# Accepted sources (first that exists and is non-empty wins for the move):
#   1) $ORCAN_DATA/worktrees
#   2) $ORCAN_PROJECTS_ROOT/worktrees   (pre-dot layout under sandbox/space)
# Target:
#   $ORCAN_PROJECTS_ROOT/.worktrees/<workspace>/<project>/
#   (default ORCAN_PROJECTS_ROOT=$ORCAN_DATA/sandbox)
#
# Run on the HOST. Safe to re-run. Never overwrites non-empty dest; never deletes.
# Rewrites absolute paths in registry.json and orcan.config.json when needed.

set -Eeuo pipefail

DATA="${ORCAN_DATA:-${XDG_CONFIG_HOME:-${HOME}/.config}/orcan}"
PROJECTS_ROOT="${ORCAN_PROJECTS_ROOT:-${DATA}/sandbox}"
NEW="${PROJECTS_ROOT}/.worktrees"

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

# Every location this migration has ever moved worktrees *from* — the
# "nothing to migrate" fast-path below must check all of these, not just a
# subset, or it can declare victory while legacy worktrees are still sitting
# in one of the others.
LEGACY_CANDIDATES=(
    "${DATA}/worktrees"
    "${PROJECTS_ROOT}/worktrees"
    "${DATA}/sandbox/worktrees"
    "${DATA}/space/worktrees"
)

any_legacy_nonempty() {
    local candidate
    for candidate in "${LEGACY_CANDIDATES[@]}"; do
        dir_nonempty "${candidate}" && return 0
    done
    return 1
}

rewrite_file_paths() {
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

pick_old() {
    local candidate
    for candidate in "${LEGACY_CANDIDATES[@]}"; do
        if dir_nonempty "${candidate}"; then
            # Skip if it already *is* the new path
            if [[ "$(cd -- "${candidate}" && pwd -P)" == "$(mkdir -p "${NEW}" && cd -- "${NEW}" && pwd -P)" ]]; then
                continue
            fi
            printf '%s\n' "${candidate}"
            return 0
        fi
    done
    return 1
}

if [[ -d "${NEW}" ]] && ! any_legacy_nonempty; then
    # Already on .worktrees and no legacy dirs (any of them) have content.
    info "nothing to migrate — already using ${NEW} (or fresh install)"
    mkdir -p "${NEW}"
    exit 0
fi

OLD=""
if ! OLD="$(pick_old)"; then
    info "nothing to migrate (no legacy worktrees dir) — ensuring ${NEW}"
    mkdir -p "${NEW}"
    exit 0
fi

info "Moving managed worktrees:"
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

rewrite_file_paths "${NEW}/registry.json" "${OLD}" "${NEW}"
for cfg in "${CONFIG_CANDIDATES[@]}"; do
    [[ -n "${cfg}" ]] || continue
    rewrite_file_paths "${cfg}" "${OLD}" "${NEW}"
done

info ""
info "Done. Next: orcan sync"
info "  (.worktrees stays under sandbox — hidden from normal project listings, same mount)"
