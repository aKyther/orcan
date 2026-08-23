#!/usr/bin/env bash
# Validate PROJECT_DIR for host-container path parity.
# Host-only: do not copy this into the Docker image.
#
# Usage:
#   validate-project-dir.sh              # reads PROJECT_DIR from .env or environment
#   validate-project-dir.sh /abs/path    # validate explicit path
#   PROJECT_DIR=/abs/path validate-project-dir.sh

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PATH_GUARDS_DIR="${ROOT_DIR}/scripts/repository"

load_project_dir() {
    local from_arg="${1:-}"
    local from_env="${PROJECT_DIR:-}"

    if [[ -n "${from_arg}" ]]; then
        printf '%s\n' "${from_arg}"
        return 0
    fi

    if [[ -n "${from_env}" ]]; then
        printf '%s\n' "${from_env}"
        return 0
    fi

    if [[ -f "${ROOT_DIR}/.env" ]]; then
        local line
        line="$(grep -E '^PROJECT_DIR=' "${ROOT_DIR}/.env" | tail -n 1 || true)"
        if [[ -n "${line}" ]]; then
            printf '%s\n' "${line#PROJECT_DIR=}"
            return 0
        fi
    fi

    printf 'Error: PROJECT_DIR is not set. Run orcan sync (or set PROJECT_DIR in .env)\n' >&2
    return 1
}

normalize_absolute_path() {
    local path="$1"
    local resolved

    if [[ "${path}" == *'~'* ]]; then
        printf 'Error: PROJECT_DIR must not contain ~ (use an absolute path)\n' >&2
        return 1
    fi

    if [[ "${path}" != /* ]]; then
        printf 'Error: PROJECT_DIR must be an absolute path (got: %s)\n' "${path}" >&2
        return 1
    fi

    if [[ ! -e "${path}" ]]; then
        printf 'Error: PROJECT_DIR does not exist: %s\n' "${path}" >&2
        return 1
    fi

    if command -v realpath >/dev/null 2>&1; then
        resolved="$(realpath "${path}")"
    else
        resolved="$(cd -- "${path}" && pwd -P)"
    fi

    printf '%s\n' "${resolved}"
}

# Uses path_guards.py (same rules as config wizard / apply-config).
reject_sensitive_path() {
    local path="$1"
    local home_dir

    home_dir="$(getent passwd "$(id -un)" 2>/dev/null | cut -d: -f6 || printf '%s' "${HOME}")"
    home_dir="${home_dir:-${HOME:-}}"

    if [[ -n "${home_dir}" && "${path}" == "${home_dir}" ]]; then
        printf 'Error: refusing to mount the entire home directory: %s\n' "${path}" >&2
        printf 'Hint: set PROJECT_DIR to a project subdirectory, for example %s/projects/my-app\n' "${home_dir}" >&2
        return 1
    fi

    if ! command -v python3 >/dev/null 2>&1; then
        printf 'Error: python3 is required to validate PROJECT_DIR (path_guards.py)\n' >&2
        return 1
    fi

    if ! PYTHONPATH="${PATH_GUARDS_DIR}" python3 -c "
from path_guards import is_sensitive_path
import sys
sys.exit(1 if is_sensitive_path(sys.argv[1]) else 0)
" "${path}"; then
        printf 'Error: refusing to mount a sensitive path: %s\n' "${path}" >&2
        return 1
    fi

    return 0
}

validate_project_dir() {
    local raw resolved

    raw="$(load_project_dir "${1:-}")" || return 1
    resolved="$(normalize_absolute_path "${raw}")" || return 1

    if [[ ! -d "${resolved}" ]]; then
        printf 'Error: PROJECT_DIR is not a directory: %s\n' "${resolved}" >&2
        return 1
    fi

    if [[ ! -r "${resolved}" ]]; then
        printf 'Error: PROJECT_DIR is not readable: %s\n' "${resolved}" >&2
        return 1
    fi

    reject_sensitive_path "${resolved}" || return 1

    # Export for callers that source this script.
    PROJECT_DIR="${resolved}"
    export PROJECT_DIR
    return 0
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    validate_project_dir "${1:-}"
fi
