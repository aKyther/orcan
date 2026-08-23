#!/usr/bin/env bash
# Integration test: adding a project to a running container must not recreate
# it, must not touch existing tmux/agent sessions, and the new project must
# become visible via a live `orcan sync` reconcile. This is the core
# acceptance criterion for runtime modification — see docs/en/ideas/
# mental-model.md and AGENTS.md "Runtime modification".
#
# Host-only helper. Requires Docker. Fully isolated from any other running
# orcan container (unique Compose project name / container name / port).

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    printf 'Skip: Docker daemon not available for runtime reconcile integration test\n'
    exit 0
fi

RUN_ID="$$"
export COMPOSE_PROJECT_NAME="orcan-reconcile-test-${RUN_ID}"
export ORCAN_INSTANCE="${RUN_ID: -4}"
export TTYD_HOST_PORT=$(( 20000 + (RUN_ID % 10000) ))
IMAGE_TAG="orcan:reconcile-test-${RUN_ID}"

BASE="$(mktemp -d "/tmp/orcan-reconcile-test-${RUN_ID}-XXXXXX")"
export ORCAN_HOME="${BASE}/home"
export ORCAN_DATA="${BASE}/home/data"
PROJECT_DIR="${BASE}/project"

cleanup() {
    ( export ORCAN_HOME ORCAN_DATA COMPOSE_PROJECT_NAME ORCAN_INSTANCE
      docker compose --project-name "${COMPOSE_PROJECT_NAME}" down >/dev/null 2>&1 || true ) || true
    docker rmi "${IMAGE_TAG}" >/dev/null 2>&1 || true
    rm -rf "${BASE}"
}
trap cleanup EXIT

printf 'Runtime reconcile integration test: %s (compose project %s)\n' "${BASE}" "${COMPOSE_PROJECT_NAME}"

mkdir -p "${PROJECT_DIR}"
git -C "${PROJECT_DIR}" init --quiet -b main
git -C "${PROJECT_DIR}" config user.email t@example.com
git -C "${PROJECT_DIR}" config user.name t
echo hello > "${PROJECT_DIR}/README.md"
git -C "${PROJECT_DIR}" add README.md
git -C "${PROJECT_DIR}" commit --quiet -m init

./bin/orcan init "${PROJECT_DIR}" >/dev/null

# TTYD_HOST_PORT comes from orcan.config.json (default 7681), not the shell
# env var apply-config.py never reads for it — patch .env directly so this
# run doesn't collide with any other orcan container's ttyd port.
sed -i "s/^TTYD_HOST_PORT=.*/TTYD_HOST_PORT=${TTYD_HOST_PORT}/" "${ORCAN_HOME}/.env"

IMAGE_LOCAL="${IMAGE_TAG}" \
    docker build -t "${IMAGE_TAG}" \
        --build-arg USER_UID="$(id -u)" \
        --build-arg USER_GID="$(id -g)" \
        --build-arg INSTALL_CURSOR=0 \
        --build-arg INSTALL_CLAUDE=1 \
        . >/dev/null

export IMAGE_LOCAL="${IMAGE_TAG}"
./bin/orcan up >/dev/null

CONTAINER="orcan-${ORCAN_INSTANCE}"

docker exec "${CONTAINER}" bash -lc 'cursor-tmux-bootstrap-workspaces || true'
docker exec "${CONTAINER}" bash -lc \
    'tmux has-session -t project 2>/dev/null || tmux new-session -d -s project'
docker exec "${CONTAINER}" bash -lc \
    "tmux send-keys -t project 'echo MARKER_START && sleep 300 && echo MARKER_END' Enter"
sleep 1

before_id="$(docker inspect "${CONTAINER}" -f '{{.Id}}')"
before_started="$(docker inspect "${CONTAINER}" -f '{{.State.StartedAt}}')"
marker_pid_before="$(docker exec "${CONTAINER}" pgrep -f 'sleep 300')"

# Add a second project *under the managed root* — the case that must not
# force a Compose bind-mount change, and therefore must not recreate.
SECOND_PROJECT="${ORCAN_PROJECTS_ROOT:-${ORCAN_DATA}/sandbox}/second-app"
mkdir -p "${SECOND_PROJECT}"
git -C "${SECOND_PROJECT}" init --quiet -b main
git -C "${SECOND_PROJECT}" config user.email t@example.com
git -C "${SECOND_PROJECT}" config user.name t
echo second > "${SECOND_PROJECT}/README.md"
git -C "${SECOND_PROJECT}" add README.md
git -C "${SECOND_PROJECT}" commit --quiet -m init

python3 -c "
import json
p = '${ORCAN_HOME}/orcan.config.json'
cfg = json.load(open(p))
cfg['workspaces'][0]['projects'].append({'name': 'second-app', 'path': '${SECOND_PROJECT}'})
json.dump(cfg, open(p, 'w'), indent=2)
"

sync_out="$(./bin/orcan sync 2>&1)"
printf '%s\n' "${sync_out}"

after_id="$(docker inspect "${CONTAINER}" -f '{{.Id}}')"
after_started="$(docker inspect "${CONTAINER}" -f '{{.State.StartedAt}}')"

fail=0

if [[ "${before_id}" != "${after_id}" ]]; then
    printf 'FAIL: container was recreated (id changed: %s -> %s)\n' "${before_id}" "${after_id}" >&2
    fail=1
fi
if [[ "${before_started}" != "${after_started}" ]]; then
    printf 'FAIL: container was restarted (StartedAt changed: %s -> %s)\n' "${before_started}" "${after_started}" >&2
    fail=1
fi
if ! printf '%s\n' "${sync_out}" | grep -q 'live reconcile complete'; then
    printf 'FAIL: sync did not report a live reconcile\n' >&2
    fail=1
fi
if ! docker exec "${CONTAINER}" pgrep -f 'sleep 300' >/dev/null 2>&1; then
    printf 'FAIL: marker process (simulating an active agent session) did not survive\n' >&2
    fail=1
fi
marker_pid_after="$(docker exec "${CONTAINER}" pgrep -f 'sleep 300' || true)"
if [[ "${marker_pid_before}" != "${marker_pid_after}" ]]; then
    printf 'FAIL: marker process PID changed (%s -> %s) — session was recreated, not preserved\n' \
        "${marker_pid_before}" "${marker_pid_after}" >&2
    fail=1
fi
if ! docker exec "${CONTAINER}" test -L /home/developer/workspaces/project/second-app; then
    printf 'FAIL: new project symlink not visible inside the running container\n' >&2
    fail=1
fi
if ! docker exec "${CONTAINER}" test -f /home/developer/workspaces/project/second-app/README.md; then
    printf 'FAIL: new project content not readable inside the running container\n' >&2
    fail=1
fi

# Idempotency: a second sync with no config change must be a clean no-op.
sync_out2="$(./bin/orcan sync 2>&1)"
if ! printf '%s\n' "${sync_out2}" | grep -q 'changed=False'; then
    printf 'FAIL: second sync (no config change) was not reported as a no-op\n' >&2
    fail=1
fi
after2_id="$(docker inspect "${CONTAINER}" -f '{{.Id}}')"
if [[ "${before_id}" != "${after2_id}" ]]; then
    printf 'FAIL: container was recreated on the idempotent second sync\n' >&2
    fail=1
fi

if (( fail )); then
    printf 'Runtime reconcile integration test FAILED\n' >&2
    exit 1
fi

printf 'Runtime reconcile integration test passed: project added live, container never recreated, tmux/agent session preserved\n'
