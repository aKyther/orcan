#!/usr/bin/env bash
# Tag / push / pull the cind image to a container registry (GitLab-friendly).
# Host-only: do not copy this into the Docker image.
#
# Usage:
#   ./scripts/repository/registry.sh show
#   ./scripts/repository/registry.sh login
#   ./scripts/repository/registry.sh publish
#   ./scripts/repository/registry.sh pull
#
# Env (from .env or shell):
#   IMAGE_LOCAL       local image name (default: cursor-dev:latest)
#   IMAGE_REGISTRY    registry host (default: registry.gitlab.com)
#   IMAGE_REPOSITORY  path under registry, e.g. mygroup/cind
#   IMAGE_TAG         tag (default: latest)
#   REGISTRY_USER     username for docker login
#   REGISTRY_PASSWORD password / PAT / deploy token (prefer stdin / env, not git)

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

if [[ -f "${ROOT_DIR}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${ROOT_DIR}/.env"
    set +a
fi

IMAGE_LOCAL="${IMAGE_LOCAL:-cursor-dev:latest}"
IMAGE_REGISTRY="${IMAGE_REGISTRY:-registry.gitlab.com}"
IMAGE_REPOSITORY="${IMAGE_REPOSITORY:-}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

# Accept common GitLab CI / deploy aliases
REGISTRY_USER="${REGISTRY_USER:-${CI_REGISTRY_USER:-${GITLAB_USER:-}}}"
REGISTRY_PASSWORD="${REGISTRY_PASSWORD:-${CI_REGISTRY_PASSWORD:-${GITLAB_TOKEN:-${CI_JOB_TOKEN:-}}}}"

die() {
    printf 'Error: %s\n' "$1" >&2
    exit 1
}

require_repository() {
    if [[ -z "${IMAGE_REPOSITORY}" ]]; then
        die "IMAGE_REPOSITORY is not set.

Example in .env:
  IMAGE_REGISTRY=registry.gitlab.com
  IMAGE_REPOSITORY=mygroup/cind
  IMAGE_TAG=latest

Then:
  make registry-login
  make publish"
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
        printf 'Local exists:  no (run: make build)\n'
    fi
}

cmd_login() {
    local user password
    user="${REGISTRY_USER}"
    password="${REGISTRY_PASSWORD}"

    if [[ -z "${user}" ]]; then
        printf 'Registry user (GitLab username or deploy-token username): '
        read -r user
    fi
    [[ -n "${user}" ]] || die "username is empty"

    if [[ -z "${password}" ]]; then
        printf 'Password / Personal Access Token / Deploy Token (input hidden): '
        read -rs password
        printf '\n'
    fi
    [[ -n "${password}" ]] || die "password/token is empty"

    printf 'Logging in to %s as %s...\n' "${IMAGE_REGISTRY}" "${user}"
    printf '%s' "${password}" | docker login "${IMAGE_REGISTRY}" -u "${user}" --password-stdin
    printf 'OK: logged in to %s\n' "${IMAGE_REGISTRY}"
    printf 'Hint: create a GitLab PAT with scopes read_registry + write_registry\n'
    printf '      or a Deploy Token with read_registry + write_registry\n'
}

cmd_publish() {
    local remote
    remote="$(remote_image)"

    if ! docker image inspect "${IMAGE_LOCAL}" >/dev/null 2>&1; then
        die "local image ${IMAGE_LOCAL} not found. Run: make build"
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
    printf 'Next: make terminal-docker\n'
}

usage() {
    cat <<'EOF'
Usage: registry.sh <show|login|publish|pull>

  show     Print configured image names
  login    docker login to IMAGE_REGISTRY (GitLab)
  publish  Tag local image and push to registry
  pull     Pull remote image and retag as local cursor-dev:latest
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
