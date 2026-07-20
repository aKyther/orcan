#!/usr/bin/env bash
# Create or refresh .env from the host identity and PROJECT_DIR.
# Host-only: do not copy this into the Docker image.

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

# shellcheck source=validate-project-dir.sh
source "${ROOT_DIR}/scripts/repository/validate-project-dir.sh"

PROJECT_DIR="${PROJECT_DIR:-${ROOT_DIR}}"
USER_UID="$(id -u)"
USER_GID="$(id -g)"
DOCKER_GID="999"

if [[ -S /var/run/docker.sock ]]; then
    DOCKER_GID="$(stat -c '%g' /var/run/docker.sock)"
fi

if [[ ! -f .env ]]; then
    cp .env.example .env
fi

validate_project_dir "${PROJECT_DIR}"
PROJECT_DIR="${PROJECT_DIR}"

sed -i "s|^USER_UID=.*|USER_UID=${USER_UID}|" .env
sed -i "s|^USER_GID=.*|USER_GID=${USER_GID}|" .env
sed -i "s|^DOCKER_GID=.*|DOCKER_GID=${DOCKER_GID}|" .env
sed -i "s|^PROJECT_DIR=.*|PROJECT_DIR=${PROJECT_DIR}|" .env

printf '.env updated (USER_UID=%s USER_GID=%s DOCKER_GID=%s)\n' \
    "${USER_UID}" "${USER_GID}" "${DOCKER_GID}"
printf 'PROJECT_DIR=%s\n' "${PROJECT_DIR}"
