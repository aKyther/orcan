#!/usr/bin/env bash
# Ensure .env and generated runtime files exist — do not regenerate them.
# Host-only: do not copy this into the Docker image.
#
# Usage: require-generated.sh
# Honours ORCAN_HOME / ORCAN_ROOT (defaults: repo root for both).

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCAN_ROOT="${ORCAN_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}"
ORCAN_HOME="${ORCAN_HOME:-${ORCAN_ROOT}}"

hint() {
    printf 'orcan:   %s\n' "$*" >&2
}

fail() {
    printf 'orcan: %s\n' "$1" >&2
    shift
    local line
    for line in "$@"; do
        hint "${line}"
    done
    exit 1
}

# shellcheck source=validate-project-dir.sh
source "${ORCAN_ROOT}/scripts/repository/validate-project-dir.sh"

if [[ ! -f "${ORCAN_HOME}/.env" ]]; then
    if [[ -f "${ORCAN_HOME}/orcan.config.json" ]]; then
        fix="orcan sync"
    else
        fix="orcan init /absolute/path/to/repo"
    fi
    fail ".env not found: ${ORCAN_HOME}/.env" \
        "orcan up needs .env plus generated mounts/* (from orcan sync)." \
        "Fix:  ${fix}" \
        "Note: orcan build only needs .env — sync is the normal way to create it."
fi

set -a
# shellcheck disable=SC1091
source "${ORCAN_HOME}/.env"
set +a

compose_file="${ORCAN_COMPOSE_PROJECTS:-${ORCAN_HOME}/mounts/compose-projects.generated.yml}"
runtime_file="${ORCAN_CONFIG_HOST:-${ORCAN_HOME}/mounts/runtime-config.json}"

missing=()
if [[ ! -f "${compose_file}" ]]; then
    missing+=("${compose_file}")
fi
if [[ ! -f "${runtime_file}" ]]; then
    missing+=("${runtime_file}")
fi

if (( ${#missing[@]} > 0 )); then
    printf 'orcan: generated runtime files missing (orcan up needs these; orcan build does not)\n' >&2
    for path in "${missing[@]}"; do
        hint "missing: ${path}"
    done
    hint "Fix:  orcan sync"
    hint "Then: orcan up   (or orcan down && orcan up if the container is already running)"
    exit 1
fi

config_file="${CONFIG:-}"
if [[ -z "${config_file}" && -f "${ORCAN_HOME}/orcan.config.json" ]]; then
    config_file="${ORCAN_HOME}/orcan.config.json"
fi
if [[ -n "${config_file}" && -f "${config_file}" ]]; then
    if [[ "${config_file}" -nt "${runtime_file}" || "${config_file}" -nt "${compose_file}" ]]; then
        fail "orcan.config.json changed since last orcan sync" \
            "config:  ${config_file}" \
            "runtime: ${runtime_file}" \
            "mounts:  ${compose_file}" \
            "Fix:  orcan sync" \
            "Then: orcan up   (or orcan down && orcan up to refresh volume mounts)" \
            "Note: config-only edits do not require orcan build."
    fi
fi

validate_project_dir || exit 1

ORCAN_DATA="${ORCAN_DATA:-${HOME}/.config/orcan}"
if [[ -z "${ORCAN_DATA}" ]]; then
    ORCAN_DATA="${HOME}/.config/orcan"
fi
for sub in cursor cursor-app claude codex cache history dotfiles sandbox; do
    mkdir -p "${ORCAN_DATA}/${sub}"
done
ORCAN_PROJECTS_ROOT="${ORCAN_PROJECTS_ROOT:-${ORCAN_DATA}/sandbox}"
mkdir -p "${ORCAN_PROJECTS_ROOT}/.worktrees"
