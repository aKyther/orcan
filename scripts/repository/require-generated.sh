#!/usr/bin/env bash
# Ensure .env and generated runtime files exist — do not regenerate them.
# Host-only: do not copy this into the Docker image.
#
# Usage: require-generated.sh

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

# shellcheck source=validate-project-dir.sh
source "${ROOT_DIR}/scripts/repository/validate-project-dir.sh"

if [[ ! -f "${ROOT_DIR}/.env" ]]; then
    printf 'Error: .env is missing.\n' >&2
    printf 'First run:  make setup PROJECT_DIR=/absolute/path/to/repo\n' >&2
    printf 'Or:         make env\n' >&2
    exit 1
fi

set -a
# shellcheck disable=SC1091
source "${ROOT_DIR}/.env"
set +a

compose_file="${CIND_COMPOSE_PROJECTS:-${ROOT_DIR}/.cind/compose-projects.generated.yml}"
runtime_file="${CIND_CONFIG_HOST:-${ROOT_DIR}/.cind/runtime-config.json}"

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
    printf 'Run:  make env\n' >&2
    printf 'After editing cind.config.yaml (or .json), always run make env before make terminal.\n' >&2
    exit 1
fi

config_file="${CONFIG:-}"
if [[ -z "${config_file}" ]]; then
    for cand in cind.config.yaml cind.config.yml cind.config.json; do
        if [[ -f "${ROOT_DIR}/${cand}" ]]; then
            config_file="${ROOT_DIR}/${cand}"
            break
        fi
    done
fi
if [[ -n "${config_file}" && -f "${config_file}" ]]; then
    if [[ "${config_file}" -nt "${runtime_file}" || "${config_file}" -nt "${compose_file}" ]]; then
        printf 'Error: cind config is newer than generated runtime files.\n' >&2
        printf '  config:  %s\n' "${config_file}" >&2
        printf '  runtime: %s\n' "${runtime_file}" >&2
        printf '  mounts:  %s\n' "${compose_file}" >&2
        printf 'Run:  make env && make down && make terminal-docker\n' >&2
        printf 'Otherwise the launcher can show new workspace names while Docker still has old mounts.\n' >&2
        exit 1
    fi
fi

validate_project_dir || exit 1

# Ensure host data tree exists (default ~/.config/cind — like poetry under ~/.config).
CIND_DATA="${CIND_DATA:-${HOME}/.config/cind}"
if [[ -z "${CIND_DATA}" ]]; then
    CIND_DATA="${HOME}/.config/cind"
fi
for sub in cursor cursor-app claude cache npm pnpm cargo go bash-history shell-history; do
    mkdir -p "${CIND_DATA}/${sub}"
done
