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
# Canonical repo path — parity bind mounts must not live under
# /home/developer/workspaces/… or Docker nests them inside the workspaces
# parent mount and apply-config sees a stale orcan-dev meta dir.
ORCAN_REPO="$(cd -- "${ROOT_DIR}" && pwd -P)"
cd "${ORCAN_REPO}"

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    printf 'Skip: Docker daemon not available for runtime reconcile integration test\n'
    exit 0
fi

RUN_ID="$$"
export COMPOSE_PROJECT_NAME="orcan-reconcile-test-${RUN_ID}"
# container_name is global in Docker (not scoped to compose project) — use the
# full pid so we never docker-exec into someone else's orcan-N stack.
export ORCAN_INSTANCE="${RUN_ID}"
export TTYD_HOST_PORT=$(( 20000 + (RUN_ID % 10000) ))
IMAGE_TAG="orcan:reconcile-test-${RUN_ID}"

# State must live under the repo checkout (path parity), not /tmp — the Docker
# daemon bind-mounts host paths; /tmp here is often container-local only.
BASE="${ORCAN_REPO}/.tmp/reconcile-${RUN_ID}"
WS_NAME="reconcile-${RUN_ID}"
rm -rf "${BASE}"
mkdir -p "${BASE}"
export ORCAN_HOME="${BASE}/home"
export ORCAN_DATA="${BASE}/home/data"
# Isolate from host ORCAN_* — a leaked ORCAN_PROJECTS_ROOT would point the
# second-project setup at a stale checkout outside ${BASE} and break git init.
export ORCAN_PROJECTS_ROOT="${ORCAN_DATA}/sandbox"
PROJECT_DIR="${BASE}/project"

cleanup() {
    ( export ORCAN_HOME ORCAN_DATA COMPOSE_PROJECT_NAME ORCAN_INSTANCE
      docker compose --project-name "${COMPOSE_PROJECT_NAME}" down --remove-orphans >/dev/null 2>&1 || true ) || true
    docker rmi "${IMAGE_TAG}" >/dev/null 2>&1 || true
    # Sandbox bind-mount may leave root-owned files — remove via a throwaway container.
    if [[ -d "${BASE}" ]]; then
        docker run --rm --user root -v "${BASE}:${BASE}" alpine:3.20 \
            rm -rf "${BASE}" >/dev/null 2>&1 || rm -rf "${BASE}" 2>/dev/null || true
    fi
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

# Drop host workspace env that would leak real dev paths into generated .env.
unset WORKSPACE_ROOT WORKSPACE_NAME WORKSPACE_META_PATH CONTAINER_PROJECT_DIR CONFIG
export WORKSPACE="${WS_NAME}"
./bin/orcan init "${PROJECT_DIR}" >/dev/null

# Patch .env after init (compose reads ORCAN_INSTANCE / TTYD_HOST_PORT from here).
sed -i "s/^ORCAN_INSTANCE=.*/ORCAN_INSTANCE=${ORCAN_INSTANCE}/" "${ORCAN_HOME}/.env"
sed -i "s/^TTYD_HOST_PORT=.*/TTYD_HOST_PORT=${TTYD_HOST_PORT}/" "${ORCAN_HOME}/.env"

_TEST_ORCAN_HOME="${ORCAN_HOME}"
_TEST_ORCAN_DATA="${ORCAN_DATA}"
_TEST_ORCAN_PROJECTS_ROOT="${ORCAN_PROJECTS_ROOT}"

# shellcheck disable=SC1091
set -a
source "${ORCAN_HOME}/.env"
set +a
ORCAN_HOME="${_TEST_ORCAN_HOME}"
ORCAN_DATA="${_TEST_ORCAN_DATA}"
ORCAN_PROJECTS_ROOT="${_TEST_ORCAN_PROJECTS_ROOT}"
export ORCAN_HOME ORCAN_DATA ORCAN_PROJECTS_ROOT
if [[ ! -f "${ORCAN_CONFIG_HOST:-${ORCAN_HOME}/mounts/runtime-config.json}" ]]; then
    printf 'FAIL: runtime config missing before orcan up\n' >&2
    exit 1
fi
export ORCAN_CONFIG_HOST

IMAGE_LOCAL="${IMAGE_TAG}" \
    docker build -t "${IMAGE_TAG}" \
        --build-arg USER_UID="$(id -u)" \
        --build-arg USER_GID="$(id -g)" \
        --build-arg INSTALL_CURSOR=0 \
        --build-arg INSTALL_CLAUDE=1 \
        . >/dev/null

export IMAGE_LOCAL="${IMAGE_TAG}"
if ! ./bin/orcan up >/dev/null; then
    printf 'FAIL: orcan up failed\n' >&2
    exit 1
fi

CONTAINER="orcan-${ORCAN_INSTANCE}"
if ! docker exec "${CONTAINER}" test -f /etc/orcan/config.json; then
    printf 'FAIL: /etc/orcan/config.json is not a file in %s (check ORCAN_CONFIG_HOST mount)\n' "${CONTAINER}" >&2
    docker exec "${CONTAINER}" ls -la /etc/orcan/ >&2 || true
    exit 1
fi

docker exec "${CONTAINER}" bash -lc 'cursor-tmux-bootstrap-workspaces || true'
if ! docker exec "${CONTAINER}" bash -lc \
    "tmux has-session -t ${WS_NAME} 2>/dev/null || tmux new-session -d -s ${WS_NAME}"; then
    printf 'FAIL: could not create tmux session %s\n' "${WS_NAME}" >&2
    exit 1
fi
if ! docker exec "${CONTAINER}" bash -lc \
    "tmux send-keys -t ${WS_NAME} 'echo MARKER_START && sleep 300 && echo MARKER_END' Enter"; then
    printf 'FAIL: could not start marker command in tmux session %s\n' "${WS_NAME}" >&2
    docker exec "${CONTAINER}" tmux capture-pane -t "${WS_NAME}" -p >&2 || true
    exit 1
fi

marker_pid_before=""
for _ in 1 2 3 4 5 6 7 8 9 10; do
    marker_pid_before="$(docker exec "${CONTAINER}" pgrep -f 'sleep 300' || true)"
    [[ -n "${marker_pid_before}" ]] && break
    sleep 1
done
if [[ -z "${marker_pid_before}" ]]; then
    printf 'FAIL: marker process (sleep 300) did not start in tmux session %s\n' "${WS_NAME}" >&2
    docker exec "${CONTAINER}" tmux capture-pane -t "${WS_NAME}" -p >&2 || true
    exit 1
fi

before_id="$(docker inspect "${CONTAINER}" -f '{{.Id}}')"
before_started="$(docker inspect "${CONTAINER}" -f '{{.State.StartedAt}}')"

# Add a second project *under the managed root* — the case that must not
# force a Compose bind-mount change, and therefore must not recreate.
SECOND_PROJECT="${ORCAN_PROJECTS_ROOT}/second-app"
rm -rf "${SECOND_PROJECT}"
mkdir -p "${SECOND_PROJECT}"
git -C "${SECOND_PROJECT}" init --quiet -b main
git -C "${SECOND_PROJECT}" config user.email t@example.com
git -C "${SECOND_PROJECT}" config user.name t
echo second > "${SECOND_PROJECT}/README.md"
git -C "${SECOND_PROJECT}" add README.md
git -C "${SECOND_PROJECT}" commit --quiet -m init

# Sandbox bind-mount may leave root-owned files — fix ownership before host sync
# prunes workspace metas or rewrites generated mounts.
docker run --rm --user root \
    -v "${ORCAN_DATA}:${ORCAN_DATA}" \
    alpine:3.20 chown -R "$(id -u):$(id -g)" "${ORCAN_DATA}" >/dev/null 2>&1 || true

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
if ! docker exec "${CONTAINER}" test -L "/home/developer/workspaces/${WS_NAME}/second-app"; then
    printf 'FAIL: new project symlink not visible inside the running container\n' >&2
    fail=1
fi
if ! docker exec "${CONTAINER}" test -f "/home/developer/workspaces/${WS_NAME}/second-app/README.md"; then
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
