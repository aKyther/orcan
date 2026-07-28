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

# shellcheck source=validate-project-dir.sh
source "${ORCAN_ROOT}/scripts/repository/validate-project-dir.sh"

if [[ ! -f "${ORCAN_HOME}/.env" ]]; then
    printf 'Error: .env is missing.\n' >&2
    printf 'First run:  orcan init /absolute/path/to/repo\n' >&2
    printf 'Or:         orcan sync\n' >&2
    exit 1
fi

set -a
# shellcheck disable=SC1091
source "${ORCAN_HOME}/.env"
set +a

compose_file="${ORCAN_COMPOSE_PROJECTS:-${ORCAN_HOME}/.orcan/compose-projects.generated.yml}"
runtime_file="${ORCAN_CONFIG_HOST:-${ORCAN_HOME}/.orcan/runtime-config.json}"

missing=()
if [[ ! -f "${compose_file}" ]]; then
    missing+=("${compose_file}")
fi
if [[ ! -f "${runtime_file}" ]]; then
    missing+=("${runtime_file}")
fi

if (( ${#missing[@]} > 0 )); then
    printf 'Error: generated runtime files are missing:\n' >&2
    for path in "${missing[@]}"; do
        printf '  - %s\n' "${path}" >&2
    done
    printf 'Run:  orcan sync\n' >&2
    printf 'After editing orcan.config.json, always run orcan sync before orcan up.\n' >&2
    exit 1
fi

config_file="${CONFIG:-}"
if [[ -z "${config_file}" && -f "${ORCAN_HOME}/orcan.config.json" ]]; then
    config_file="${ORCAN_HOME}/orcan.config.json"
fi
if [[ -n "${config_file}" && -f "${config_file}" ]]; then
    if [[ "${config_file}" -nt "${runtime_file}" || "${config_file}" -nt "${compose_file}" ]]; then
        printf 'Error: orcan config is newer than generated runtime files.\n' >&2
        printf '  config:  %s\n' "${config_file}" >&2
        printf '  runtime: %s\n' "${runtime_file}" >&2
        printf '  mounts:  %s\n' "${compose_file}" >&2
        printf 'Run:  orcan sync && orcan down && orcan up\n' >&2
        printf 'Otherwise the launcher can show new workspace names while Docker still has old mounts.\n' >&2
        exit 1
    fi
fi

validate_project_dir || exit 1

ORCAN_DATA="${ORCAN_DATA:-${HOME}/.config/orcan}"
if [[ -z "${ORCAN_DATA}" ]]; then
    ORCAN_DATA="${HOME}/.config/orcan"
fi
for sub in cursor cursor-app claude cache npm pnpm cargo go bash-history shell-history worktrees; do
    mkdir -p "${ORCAN_DATA}/${sub}"
done
