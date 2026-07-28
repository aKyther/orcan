#!/usr/bin/env bash
# Create or refresh .env from host identity + optional orcan.config.json.
# Host-only: do not copy this into the Docker image.
#
# ORCAN_ROOT = install/clone (scripts, compose, Dockerfile)
# ORCAN_HOME = user config + .env + .orcan/* (defaults to ORCAN_ROOT for legacy)

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCAN_ROOT="${ORCAN_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}"
ORCAN_HOME="${ORCAN_HOME:-${ORCAN_ROOT}}"
mkdir -p "${ORCAN_HOME}"
cd "${ORCAN_HOME}"

# shellcheck source=validate-project-dir.sh
source "${ORCAN_ROOT}/scripts/repository/validate-project-dir.sh"

REQUESTED_PROJECT_DIR="${PROJECT_DIR:-${ORCAN_HOME}}"
CONFIG="${CONFIG:-}"
USER_UID="$(id -u)"
USER_GID="$(id -g)"
DOCKER_GID="999"

if [[ -S /var/run/docker.sock ]]; then
    DOCKER_GID="$(stat -c '%g' /var/run/docker.sock)"
fi

# Seed .env.example into home when using a split ORCAN_HOME.
if [[ ! -f "${ORCAN_HOME}/.env.example" && -f "${ORCAN_ROOT}/.env.example" ]]; then
    cp -- "${ORCAN_ROOT}/.env.example" "${ORCAN_HOME}/.env.example"
fi

if [[ ! -f .env ]]; then
    if [[ -f .env.example ]]; then
        cp .env.example .env
    elif [[ -f "${ORCAN_ROOT}/.env.example" ]]; then
        cp -- "${ORCAN_ROOT}/.env.example" .env
    else
        printf 'Error: missing .env.example\n' >&2
        exit 1
    fi
fi

ensure_env_key() {
    local key="$1"
    local value="$2"
    if grep -qE "^${key}=" .env; then
        sed -i "s|^${key}=.*|${key}=${value}|" .env
    else
        printf '%s=%s\n' "${key}" "${value}" >> .env
    fi
}

# Prefer explicit CONFIG, else orcan.config.json in home (or legacy root).
if [[ -z "${CONFIG}" && -f "${ORCAN_HOME}/orcan.config.json" ]]; then
    CONFIG="${ORCAN_HOME}/orcan.config.json"
fi
if [[ -z "${CONFIG}" && -f "${ORCAN_ROOT}/orcan.config.json" ]]; then
    CONFIG="${ORCAN_ROOT}/orcan.config.json"
fi

apply_args=(
    --root "${ORCAN_HOME}"
    --project-dir "${REQUESTED_PROJECT_DIR}"
)
if [[ -n "${CONFIG}" ]]; then
    apply_args+=(--config "${CONFIG}")
fi

"${ORCAN_ROOT}/scripts/repository/python.sh" \
    "${ORCAN_ROOT}/scripts/repository/apply-config.py" "${apply_args[@]}"

# Re-read paths written by apply-config, then validate default project path.
# shellcheck disable=SC1091
set -a
# shellcheck source=/dev/null
source "${ORCAN_HOME}/.env"
set +a

validate_project_dir "${PROJECT_DIR}"

ensure_env_key "USER_UID" "${USER_UID}"
ensure_env_key "USER_GID" "${USER_GID}"
ensure_env_key "DOCKER_GID" "${DOCKER_GID}"

detect_host_tz() {
    local tz=""
    if [[ -f /etc/timezone ]]; then
        tz="$(tr -d '[:space:]' </etc/timezone || true)"
    fi
    if [[ -z "${tz}" ]] && command -v timedatectl >/dev/null 2>&1; then
        tz="$(timedatectl show -p Timezone --value 2>/dev/null || true)"
    fi
    if [[ -z "${tz}" && -L /etc/localtime ]]; then
        tz="$(readlink -f /etc/localtime 2>/dev/null | sed -n 's|.*/zoneinfo/||p' || true)"
    fi
    if [[ -z "${tz}" ]]; then
        tz="UTC"
    fi
    printf '%s\n' "${tz}"
}

if ! grep -qE '^TZ=.' .env; then
    ensure_env_key "TZ" "$(detect_host_tz)"
fi

if [[ -z "${ORCAN_DATA:-}" ]]; then
    ORCAN_DATA="${HOME}/.config/orcan"
fi
if ! grep -qE '^ORCAN_DATA=.' .env; then
    ensure_env_key "ORCAN_DATA" "${ORCAN_DATA}"
fi

ORCAN_DATA_SUBDIRS=(
    cursor
    cursor-app
    claude
    cache
    npm
    pnpm
    cargo
    go
    bash-history
    shell-history
)
mkdir -p "${ORCAN_DATA}"
for sub in "${ORCAN_DATA_SUBDIRS[@]}"; do
    mkdir -p "${ORCAN_DATA}/${sub}"
done
if chown -R "${USER_UID}:${USER_GID}" "${ORCAN_DATA}" 2>/dev/null; then
    :
else
    printf 'Warning: could not chown %s (UID=%s GID=%s); fix ownership if mounts fail\n' \
        "${ORCAN_DATA}" "${USER_UID}" "${USER_GID}" >&2
fi

printf '.env updated (USER_UID=%s USER_GID=%s DOCKER_GID=%s TZ=%s)\n' \
    "${USER_UID}" "${USER_GID}" "${DOCKER_GID}" "$(grep -E '^TZ=' .env | cut -d= -f2-)"
printf 'ORCAN_HOME=%s\n' "${ORCAN_HOME}"
printf 'ORCAN_ROOT=%s\n' "${ORCAN_ROOT}"
printf 'PROJECT_DIR=%s\n' "${PROJECT_DIR}"
printf 'ORCAN_DATA=%s (host config/cache — created if missing)\n' "${ORCAN_DATA}"
if [[ -n "${CONFIG}" ]]; then
    printf 'CONFIG=%s\n' "${CONFIG}"
fi
if [[ -f "${ORCAN_COMPOSE_PROJECTS:-${ORCAN_HOME}/.orcan/compose-projects.generated.yml}" ]]; then
    printf 'project mounts: %s\n' "${ORCAN_COMPOSE_PROJECTS:-${ORCAN_HOME}/.orcan/compose-projects.generated.yml}"
fi
printf 'Next: orcan down && orcan up\n'
