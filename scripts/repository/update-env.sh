#!/usr/bin/env bash
# Create or refresh .env from host identity + optional orcan.config.json.
# Host-only: do not copy this into the Docker image.
#
# ORCAN_ROOT = install/clone (scripts, compose, Dockerfile)
# ORCAN_HOME = user config + .env + mounts/* (defaults to ORCAN_ROOT for legacy)

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
    local tmp line
    if grep -qE "^${key}=" .env; then
        tmp="$(mktemp)"
        while IFS= read -r line || [[ -n "${line}" ]]; do
            if [[ "${line}" == "${key}="* ]]; then
                printf '%s=%s\n' "${key}" "${value}"
            else
                printf '%s\n' "${line}"
            fi
        done < .env >"${tmp}"
        mv -- "${tmp}" .env
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

# Resolved early (before apply-config.py) so it can see ORCAN_PROJECTS_ROOT
# and skip generating a per-project Compose bind for anything already under
# it — the managed root itself is a stable mount in docker-compose.yml, so
# leaving those paths out of the generated overlay is what lets adding a
# managed project skip a container recreate.
if [[ -z "${ORCAN_DATA:-}" ]]; then
    ORCAN_DATA="${HOME}/.config/orcan"
fi
export ORCAN_DATA
ORCAN_PROJECTS_ROOT="${ORCAN_PROJECTS_ROOT:-${ORCAN_DATA}/sandbox}"
export ORCAN_PROJECTS_ROOT
mkdir -p "${ORCAN_PROJECTS_ROOT}"
# .env(.example) ships both as empty placeholders — `source .env` below
# would otherwise blank out the values just resolved. Snapshot them now,
# restore verbatim after sourcing (no need to re-derive defaults there).
_RESOLVED_ORCAN_DATA="${ORCAN_DATA}"
_RESOLVED_ORCAN_PROJECTS_ROOT="${ORCAN_PROJECTS_ROOT}"

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

# source .env above can overwrite UID/GID/DOCKER_GID with stale values (e.g.
# DOCKER_GID=999 from .env.example). Always re-detect from the host.
USER_UID="$(id -u)"
USER_GID="$(id -g)"
DOCKER_GID="999"
if [[ -S /var/run/docker.sock ]]; then
    DOCKER_GID="$(stat -c '%g' /var/run/docker.sock)"
fi

# Restore the ORCAN_DATA/ORCAN_PROJECTS_ROOT snapshot taken before the
# source above — see the comment there.
ORCAN_DATA="${_RESOLVED_ORCAN_DATA}"
export ORCAN_DATA
ORCAN_PROJECTS_ROOT="${_RESOLVED_ORCAN_PROJECTS_ROOT}"
export ORCAN_PROJECTS_ROOT

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

# Quote a value for Docker Compose .env (double-quoted; escape \ and ").
quote_dotenv() {
    local v="$1"
    v="${v//\\/\\\\}"
    v="${v//\"/\\\"}"
    printf '"%s"' "${v}"
}

# Host git identity → container commits match host author/committer.
# Prefer global config (update-env cwd is ORCAN_HOME, not a project repo).
# SSH keys / agent are NOT mounted here — use: orcan up --with-git
GIT_AUTHOR_NAME="$(git config --global --get user.name 2>/dev/null || true)"
GIT_AUTHOR_EMAIL="$(git config --global --get user.email 2>/dev/null || true)"
if [[ -n "${GIT_AUTHOR_NAME}" ]]; then
    ensure_env_key "GIT_AUTHOR_NAME" "$(quote_dotenv "${GIT_AUTHOR_NAME}")"
    ensure_env_key "GIT_COMMITTER_NAME" "$(quote_dotenv "${GIT_AUTHOR_NAME}")"
else
    printf 'Warning: host git user.name unset — commits inside the container may lack identity\n' >&2
fi
if [[ -n "${GIT_AUTHOR_EMAIL}" ]]; then
    ensure_env_key "GIT_AUTHOR_EMAIL" "$(quote_dotenv "${GIT_AUTHOR_EMAIL}")"
    ensure_env_key "GIT_COMMITTER_EMAIL" "$(quote_dotenv "${GIT_AUTHOR_EMAIL}")"
else
    printf 'Warning: host git user.email unset — commits inside the container may lack identity\n' >&2
fi

if ! grep -qE '^ORCAN_DATA=.' .env; then
    ensure_env_key "ORCAN_DATA" "${ORCAN_DATA}"
fi
if ! grep -qE '^ORCAN_PROJECTS_ROOT=.' .env; then
    ensure_env_key "ORCAN_PROJECTS_ROOT" "${ORCAN_PROJECTS_ROOT}"
fi

ORCAN_DATA_SUBDIRS=(
    cursor
    cursor-app
    claude
    codex
    cache
    history
    dotfiles
    context
    sandbox
    state
)
mkdir -p "${ORCAN_DATA}"
for sub in "${ORCAN_DATA_SUBDIRS[@]}"; do
    mkdir -p "${ORCAN_DATA}/${sub}"
done
# Managed worktrees live under the projects root (Compose bind) so adding one
# does not require a container recreate. Legacy: $ORCAN_DATA/worktrees — see
# scripts/migrations/move-worktrees-into-sandbox.sh.
mkdir -p "${ORCAN_PROJECTS_ROOT}/.worktrees"

# Seed example overlays once (never overwrite user files).
DOTFILES_SRC="${ORCAN_ROOT}/docker/rootfs/opt/orcan/dotfiles"
DOTFILES_DST="${ORCAN_DATA}/dotfiles"
if [[ -d "${DOTFILES_SRC}" ]]; then
    mkdir -p "${DOTFILES_DST}/zshrc.d" "${DOTFILES_DST}/bashrc.d"
    if [[ -f "${DOTFILES_SRC}/README.md" && ! -e "${DOTFILES_DST}/README.md" ]]; then
        cp -- "${DOTFILES_SRC}/README.md" "${DOTFILES_DST}/README.md"
    fi
    for src in "${DOTFILES_SRC}"/*.example "${DOTFILES_SRC}"/zshrc.d/*.example; do
        [[ -f "${src}" ]] || continue
        rel="${src#"${DOTFILES_SRC}/"}"
        dst="${DOTFILES_DST}/${rel}"
        mkdir -p "$(dirname "${dst}")"
        if [[ ! -e "${dst}" ]]; then
            cp -- "${src}" "${dst}"
        fi
    done
fi

if chown -R "${USER_UID}:${USER_GID}" "${ORCAN_DATA}" 2>/dev/null; then
    :
else
    printf 'Warning: could not chown %s (UID=%s GID=%s); fix ownership if mounts fail\n' \
        "${ORCAN_DATA}" "${USER_UID}" "${USER_GID}" >&2
fi

printf '.env updated (USER_UID=%s USER_GID=%s DOCKER_GID=%s TZ=%s)\n' \
    "${USER_UID}" "${USER_GID}" "${DOCKER_GID}" "$(grep -E '^TZ=' .env | cut -d= -f2-)"
if [[ -n "${GIT_AUTHOR_NAME}" || -n "${GIT_AUTHOR_EMAIL}" ]]; then
    printf 'git identity: %s <%s>\n' \
        "${GIT_AUTHOR_NAME:-?}" "${GIT_AUTHOR_EMAIL:-?}"
fi
printf 'user dotfiles: %s  (aliases / tmux / vim / zsh — see README there)\n' "${DOTFILES_DST}"
printf 'ORCAN_HOME=%s\n' "${ORCAN_HOME}"
printf 'ORCAN_ROOT=%s\n' "${ORCAN_ROOT}"
printf 'PROJECT_DIR=%s\n' "${PROJECT_DIR}"
printf 'ORCAN_DATA=%s (host config/cache — created if missing)\n' "${ORCAN_DATA}"
printf 'ORCAN_PROJECTS_ROOT=%s (managed project root — bind-mounted once; see docker-compose.yml)\n' "${ORCAN_PROJECTS_ROOT}"
if [[ -n "${CONFIG}" ]]; then
    printf 'CONFIG=%s\n' "${CONFIG}"
fi
if [[ -f "${ORCAN_COMPOSE_PROJECTS:-${ORCAN_HOME}/mounts/compose-projects.generated.yml}" ]]; then
    printf 'project mounts: %s\n' "${ORCAN_COMPOSE_PROJECTS:-${ORCAN_HOME}/mounts/compose-projects.generated.yml}"
fi
printf 'SSH keys: orcan up --with-git (not mounted by sync)\n'
printf 'Next: orcan down && orcan up\n'
