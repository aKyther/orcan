#!/usr/bin/env bash
# Generate runtime artifacts from orcan.config.json and host identity.
# Host-only: do not copy this into the Docker image.
#
# ORCAN_ROOT = install/clone (scripts, compose, Dockerfile)
# ORCAN_HOME = user config + generated mounts/* (defaults to ORCAN_ROOT for legacy)

set -Eeuo pipefail

ownership_args=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-chown)
            [[ $# -gt 1 && -n "$2" && "$2" != --* && "$2" != */* ]] || {
                printf 'Error: --no-chown requires a directory name or glob without slashes\n' >&2
                exit 2
            }
            ownership_args+=(--pattern "$2")
            shift 2
            ;;
        --chown-exclude)
            [[ $# -gt 1 && "$2" == /* ]] || {
                printf 'Error: --chown-exclude requires an absolute directory path\n' >&2
                exit 2
            }
            ownership_args+=(--exclude "$2")
            shift 2
            ;;
        *) printf 'Error: unknown sync-runtime argument: %s\n' "$1" >&2; exit 2 ;;
    esac
done

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

# Prefer explicit CONFIG, else orcan.config.json in home (or legacy root).
if [[ -z "${CONFIG}" && -f "${ORCAN_HOME}/orcan.config.json" ]]; then
    CONFIG="${ORCAN_HOME}/orcan.config.json"
fi
if [[ -z "${CONFIG}" && -f "${ORCAN_ROOT}/orcan.config.json" ]]; then
    CONFIG="${ORCAN_ROOT}/orcan.config.json"
fi

# Validate/save the ownership policy before materializing runtime files or walking data.
# Used by explicit sync and initialization; startup must not call this pipeline.
ownership_config="${CONFIG:-${ORCAN_HOME}/orcan.config.json}"
"${ORCAN_ROOT}/scripts/repository/python.sh" \
    "${ORCAN_ROOT}/scripts/repository/data-ownership.py" \
    --config "${ownership_config}" --save-policy --check-only "${ownership_args[@]}"
if (( ${#ownership_args[@]} )); then
    printf 'Ownership exclusions saved in %s; future sync/init calls reuse them\n' "${ownership_config}"
fi

# Resolve JSON paths before generating mounts; the same resolver serves the CLI.
exports="$("${ORCAN_ROOT}/scripts/repository/python.sh" "${ORCAN_ROOT}/scripts/repository/runtime-settings.py" --home "${ORCAN_HOME}" --config "${CONFIG}")"
eval "${exports}"
mkdir -p "${ORCAN_PROJECTS_ROOT}"

apply_args=(
    --root "${ORCAN_HOME}"
    --project-dir "${REQUESTED_PROJECT_DIR}"
)
if [[ -n "${CONFIG}" ]]; then
    apply_args+=(--config "${CONFIG}")
fi

"${ORCAN_ROOT}/scripts/repository/python.sh" \
    "${ORCAN_ROOT}/scripts/repository/apply-config.py" "${apply_args[@]}"

# Read validated JSON-derived settings, never source a dotenv file.
exports="$("${ORCAN_ROOT}/scripts/repository/python.sh" "${ORCAN_ROOT}/scripts/repository/runtime-settings.py" --home "${ORCAN_HOME}" --config "${CONFIG}")"
eval "${exports}"
validate_project_dir "${PROJECT_DIR}"
if [[ -f "${ORCAN_HOME}/.env" ]]; then
    printf 'Warning: legacy .env is ignored and left unchanged; move non-secret settings to orcan.config.json (see configuration guide).\n' >&2
fi

ORCAN_DATA_SUBDIRS=(
    cursor
    cursor-app
    claude
    codex
    gemini
    copilot
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

ownership_cmd=("${ORCAN_ROOT}/scripts/repository/python.sh"
    "${ORCAN_ROOT}/scripts/repository/data-ownership.py"
    --config "${ownership_config}"
    --uid "${USER_UID}" --gid "${USER_GID}" --root "${ORCAN_DATA}")
if "${ownership_cmd[@]}" 2>/dev/null; then
    :
else
    printf 'Warning: could not chown %s (UID=%s GID=%s); fix ownership if mounts fail\n' \
        "${ORCAN_DATA}" "${USER_UID}" "${USER_GID}" >&2
fi

printf 'Runtime JSON updated (USER_UID=%s USER_GID=%s DOCKER_GID=%s TZ=%s)\n' "${USER_UID}" "${USER_GID}" "${DOCKER_GID}" "${TZ}"
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
printf 'SSH keys: orcan up --ssh (not mounted by sync)\n'
printf 'Runtime files prepared; workspace reconciliation follows in orcan sync.\n'
