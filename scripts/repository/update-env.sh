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

# Match host timezone (compose passes TZ=; /etc/localtime is also bind-mounted).
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
# Set TZ from the host only when missing/empty — keep an explicit .env override.
if ! grep -qE '^TZ=.' .env; then
    ensure_env_key "TZ" "$(detect_host_tz)"
fi

# Host data root — always on (like poetry/pip under ~/.config).
# Default: $HOME/.config/cind. Override in .env only for a custom path.
# Do not overwrite an existing non-empty CIND_DATA.
if [[ -z "${CIND_DATA:-}" ]]; then
    CIND_DATA="${HOME}/.config/cind"
fi
# Persist absolute path in .env when missing or empty (make env always enables it).
if ! grep -qE '^CIND_DATA=.' .env; then
    ensure_env_key "CIND_DATA" "${CIND_DATA}"
fi

CIND_DATA_SUBDIRS=(
    cursor
    cursor-app
    claude
    cache
    npm
    pnpm
    cargo
    go
    bash-history
)
mkdir -p "${CIND_DATA}"
for sub in "${CIND_DATA_SUBDIRS[@]}"; do
    mkdir -p "${CIND_DATA}/${sub}"
done
if chown -R "${USER_UID}:${USER_GID}" "${CIND_DATA}" 2>/dev/null; then
    :
else
    printf 'Warning: could not chown %s (UID=%s GID=%s); fix ownership if mounts fail\n' \
        "${CIND_DATA}" "${USER_UID}" "${USER_GID}" >&2
fi

printf '.env updated (USER_UID=%s USER_GID=%s DOCKER_GID=%s TZ=%s)\n' \
    "${USER_UID}" "${USER_GID}" "${DOCKER_GID}" "$(grep -E '^TZ=' .env | cut -d= -f2-)"
printf 'PROJECT_DIR=%s\n' "${PROJECT_DIR}"
printf 'CIND_DATA=%s (host config/cache — created if missing)\n' "${CIND_DATA}"
if [[ -n "${CONFIG}" ]]; then
    printf 'CONFIG=%s\n' "${CONFIG}"
fi
if [[ -f "${CIND_COMPOSE_PROJECTS:-${ROOT_DIR}/.cind/compose-projects.generated.yml}" ]]; then
    printf 'project mounts: %s\n' "${CIND_COMPOSE_PROJECTS:-${ROOT_DIR}/.cind/compose-projects.generated.yml}"
fi
