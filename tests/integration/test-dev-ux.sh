#!/usr/bin/env bash
# Real-Docker lifecycle test for the isolated developer UX environment.
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
RUN_ID="$$"
STATE_ROOT="${ROOT_DIR}/.tmp/dev-ux-integration-${RUN_ID}"
PROJECT="orcan-dev-ux-test-${RUN_ID}"
INSTANCE="dev-ux-test-${RUN_ID}"
PORT="$((20000 + RUN_ID % 20000))"
MAIN_BEFORE="$(docker inspect --format '{{.Id}}' orcan-1 2>/dev/null || true)"

export ORCAN_PREVIEW_ROOT="${STATE_ROOT}"
export ORCAN_PREVIEW_PROJECT="${PROJECT}"
export ORCAN_PREVIEW_INSTANCE="${INSTANCE}"
export ORCAN_PREVIEW_PORT="${PORT}"
export ORCAN_PREVIEW_BIND="127.0.0.1"
export ORCAN_PREVIEW_SCENARIO="long-names"

cleanup() {
    "${ROOT_DIR}/scripts/dev/orcan-preview" stop >/dev/null 2>&1 || true
    rm -rf -- "${STATE_ROOT}"
}
trap cleanup EXIT

docker info >/dev/null 2>&1 || { printf 'SKIP: Docker daemon unavailable\n'; exit 0; }
docker image inspect orcan:dev-ux >/dev/null 2>&1 \
    || { printf 'SKIP: run make dev-start once to build orcan:dev-ux\n'; exit 0; }

"${ROOT_DIR}/scripts/dev/orcan-preview" start
"${ROOT_DIR}/scripts/dev/orcan-preview" doctor
"${ROOT_DIR}/scripts/dev/orcan-preview" smoke

CONTAINER="orcan-${INSTANCE}"
[[ "$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "${CONTAINER}")" == "${PROJECT}" ]]
[[ "$(docker inspect --format '{{.State.Health.Status}}' "${CONTAINER}")" == "healthy" ]]
docker exec "${CONTAINER}" curl -fsS http://127.0.0.1:7681/ >/dev/null
docker exec "${CONTAINER}" test -f /home/developer/workspaces/dev-ux/orcan/scripts/dev/orcan-preview

"${ROOT_DIR}/scripts/dev/orcan-preview" stop
! docker inspect "${CONTAINER}" >/dev/null 2>&1

MAIN_AFTER="$(docker inspect --format '{{.Id}}' orcan-1 2>/dev/null || true)"
[[ "${MAIN_AFTER}" == "${MAIN_BEFORE}" ]] || {
    printf 'FAIL: orcan-1 identity changed during isolated test\n' >&2
    exit 1
}
printf 'Developer UX Docker integration test OK (orcan-1 unchanged)\n'
