#!/usr/bin/env bash
# Create or refresh .env from host identity + optional cind.config.json.
# Host-only: do not copy this into the Docker image.

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

# shellcheck source=validate-project-dir.sh
source "${ROOT_DIR}/scripts/repository/validate-project-dir.sh"

REQUESTED_PROJECT_DIR="${PROJECT_DIR:-${ROOT_DIR}}"
CONFIG="${CONFIG:-}"
USER_UID="$(id -u)"
USER_GID="$(id -g)"
DOCKER_GID="999"

if [[ -S /var/run/docker.sock ]]; then
    DOCKER_GID="$(stat -c '%g' /var/run/docker.sock)"
fi

if [[ ! -f .env ]]; then
    cp .env.example .env
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

# Prefer explicit CONFIG, else local cind.config.json when present.
if [[ -z "${CONFIG}" && -f "${ROOT_DIR}/cind.config.json" ]]; then
    CONFIG="${ROOT_DIR}/cind.config.json"
fi

apply_args=(
    --root "${ROOT_DIR}"
    --project-dir "${REQUESTED_PROJECT_DIR}"
)
if [[ -n "${CONFIG}" ]]; then
    apply_args+=(--config "${CONFIG}")
fi

python3 "${ROOT_DIR}/scripts/repository/apply-config.py" "${apply_args[@]}"

# Re-read paths written by apply-config, then validate default project path.
# shellcheck disable=SC1091
set -a
# shellcheck source=/dev/null
source "${ROOT_DIR}/.env"
set +a

validate_project_dir "${PROJECT_DIR}"

ensure_env_key "USER_UID" "${USER_UID}"
ensure_env_key "USER_GID" "${USER_GID}"
ensure_env_key "DOCKER_GID" "${DOCKER_GID}"

printf '.env updated (USER_UID=%s USER_GID=%s DOCKER_GID=%s)\n' \
    "${USER_UID}" "${USER_GID}" "${DOCKER_GID}"
printf 'PROJECT_DIR=%s\n' "${PROJECT_DIR}"
if [[ -n "${CONFIG}" ]]; then
    printf 'CONFIG=%s\n' "${CONFIG}"
fi
if [[ -f "${CIND_COMPOSE_PROJECTS:-${ROOT_DIR}/.cind/compose-projects.generated.yml}" ]]; then
    printf 'project mounts: %s\n' "${CIND_COMPOSE_PROJECTS:-${ROOT_DIR}/.cind/compose-projects.generated.yml}"
fi
