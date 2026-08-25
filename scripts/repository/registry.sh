#!/usr/bin/env bash
# Tag / push / pull the orcan image to a container registry.
# Host-only: do not copy this into the Docker image.
#
# Usage:
#   ./scripts/repository/registry.sh show
#   ./scripts/repository/registry.sh login
#   ./scripts/repository/registry.sh publish
#   ./scripts/repository/registry.sh pull
#
# Env (from ORCAN_HOME/.env, repo .env, or shell):
#   IMAGE_LOCAL       local image name (default: orcan:latest)
#   IMAGE_REGISTRY    registry host (default: ghcr.io)
#   IMAGE_REPOSITORY  path under registry (default: akyther/orcan)
#   IMAGE_TAG         tag (default: product SemVer from cockpit/pyproject.toml / VERSION mirror)
#   REGISTRY_USER     username for docker login
#   REGISTRY_PASSWORD password / PAT / deploy token (prefer stdin / env, not git)

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

ORCAN_HOME="${ORCAN_HOME:-${ROOT_DIR}}"
ENV_CANDIDATES=("${ORCAN_HOME}/.env" "${ROOT_DIR}/.env")
for envf in "${ENV_CANDIDATES[@]}"; do
    if [[ -f "${envf}" ]]; then
        set -a
        # shellcheck disable=SC1090
        source "${envf}"
        set +a
        break
    fi
done

IMAGE_LOCAL="${IMAGE_LOCAL:-orcan:latest}"
IMAGE_REGISTRY="${IMAGE_REGISTRY:-ghcr.io}"
IMAGE_REPOSITORY="${IMAGE_REPOSITORY:-akyther/orcan}"
if [[ -z "${IMAGE_TAG:-}" ]]; then
    IMAGE_TAG="$(tr -d '[:space:]' < "${ROOT_DIR}/VERSION" 2>/dev/null || echo latest)"
fi

# Accept common GitLab CI / deploy aliases
REGISTRY_USER="${REGISTRY_USER:-${CI_REGISTRY_USER:-${GITLAB_USER:-${GITHUB_ACTOR:-}}}}"
REGISTRY_PASSWORD="${REGISTRY_PASSWORD:-${CI_REGISTRY_PASSWORD:-${GITLAB_TOKEN:-${CI_JOB_TOKEN:-${GHCR_TOKEN:-${GITHUB_TOKEN:-}}}}}}"

die() {
    printf 'Error: %s\n' "$1" >&2
    exit 1
}

require_repository() {
    if [[ -z "${IMAGE_REPOSITORY}" ]]; then
        die "IMAGE_REPOSITORY is not set.

Example in .env:
  IMAGE_REGISTRY=ghcr.io
  IMAGE_REPOSITORY=akyther/orcan
  IMAGE_TAG=0.1.1

Then:
  orcan publish
  # or: make registry-login (maintainers)"
    fi
}

remote_image() {
    require_repository
    printf '%s/%s:%s\n' "${IMAGE_REGISTRY}" "${IMAGE_REPOSITORY}" "${IMAGE_TAG}"
}

cmd_show() {
    printf 'Local image:   %s\n' "${IMAGE_LOCAL}"
    if [[ -n "${IMAGE_REPOSITORY}" ]]; then
        printf 'Remote image:  %s/%s:%s\n' "${IMAGE_REGISTRY}" "${IMAGE_REPOSITORY}" "${IMAGE_TAG}"
    else
        printf 'Remote image:  (set IMAGE_REPOSITORY in .env)\n'
    fi
    printf 'Registry:      %s\n' "${IMAGE_REGISTRY}"
    printf 'User:          %s\n' "${REGISTRY_USER:-"(not set — make registry-login will ask)"}"
    if docker image inspect "${IMAGE_LOCAL}" >/dev/null 2>&1; then
        printf 'Local exists:  yes\n'
    else
        printf 'Local exists:  no (run: orcan build)\n'
    fi
}

cmd_login() {
    local user password
    user="${REGISTRY_USER}"
    password="${REGISTRY_PASSWORD}"

    if [[ -z "${user}" ]]; then
        printf 'Registry user (GitHub username for ghcr.io): '
        read -r user
    fi
    [[ -n "${user}" ]] || die "username is empty"

    if [[ -z "${password}" ]]; then
        printf 'Password / PAT / Deploy Token (input hidden): '
        read -rs password
        printf '\n'
    fi
    [[ -n "${password}" ]] || die "password/token is empty"

    printf 'Logging in to %s as %s...\n' "${IMAGE_REGISTRY}" "${user}"
    printf '%s' "${password}" | docker login "${IMAGE_REGISTRY}" -u "${user}" --password-stdin
    printf 'OK: logged in to %s\n' "${IMAGE_REGISTRY}"
    printf 'Hint: for ghcr.io use a GitHub PAT with write:packages (and read:packages)\n'
}

cmd_publish() {
    local remote
    remote="$(remote_image)"

    if ! docker image inspect "${IMAGE_LOCAL}" >/dev/null 2>&1; then
        die "local image ${IMAGE_LOCAL} not found. Run: orcan build --force"
    fi

    printf 'Tagging %s → %s\n' "${IMAGE_LOCAL}" "${remote}"
    docker tag "${IMAGE_LOCAL}" "${remote}"
    printf 'Pushing %s\n' "${remote}"
    docker push "${remote}"
    printf 'OK: published %s\n' "${remote}"
}

cmd_pull() {
    local remote
    remote="$(remote_image)"

    printf 'Pulling %s\n' "${remote}"
    docker pull "${remote}"
    printf 'Tagging %s → %s (for Compose)\n' "${remote}" "${IMAGE_LOCAL}"
    docker tag "${remote}" "${IMAGE_LOCAL}"
    printf 'OK: ready as %s\n' "${IMAGE_LOCAL}"
    printf 'Next: orcan up\n'
}

usage() {
    cat <<'EOF'
Usage: registry.sh <show|login|publish|pull>

  show     Print configured image names
  login    docker login to IMAGE_REGISTRY
  publish  Tag local image and push to registry
  pull     Pull remote image and retag as local orcan:latest

Prefer the CLI when installed:
  orcan build     # pull VERSION; on miss build locally (never publishes)
  orcan pull
  orcan publish   # manual; maintainers only
EOF
}

case "${1:-}" in
    show) cmd_show ;;
    login) cmd_login ;;
    publish) cmd_publish ;;
    pull) cmd_pull ;;
    -h|--help|help|"") usage; [[ -n "${1:-}" ]] || exit 1 ;;
    *) die "unknown command: $1 (try: show|login|publish|pull)" ;;
esac
