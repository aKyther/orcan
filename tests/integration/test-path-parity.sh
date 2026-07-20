#!/usr/bin/env bash
# Integration test: host-container path parity with Docker socket bind mounts.
# Host-only helper. Requires Docker.

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    printf 'Skip: Docker daemon not available for path parity integration test\n'
    exit 0
fi

if [[ ! -S /var/run/docker.sock ]]; then
    printf 'Skip: /var/run/docker.sock not available\n'
    exit 0
fi

TEST_DIR="$(mktemp -d /tmp/cind-path-parity-XXXXXX)"
COMPOSE_PROJECT="cind-parity-test-$$"
COMPOSE_FILE="${TEST_DIR}/docker-compose.yml"
MARKER="parity-marker-$$"

cleanup() {
    docker compose -f "${COMPOSE_FILE}" --project-name "${COMPOSE_PROJECT}" down --remove-orphans >/dev/null 2>&1 || true
    rm -rf "${TEST_DIR}"
}

trap cleanup EXIT

printf 'Path parity integration test directory: %s\n' "${TEST_DIR}"

cat > "${COMPOSE_FILE}" <<EOF
services:
  test:
    image: alpine:3.20
    working_dir: /app
    volumes:
      - .:/app
    command:
      - sh
      - -c
      - test -f /app/${MARKER} && test -f /app/docker-compose.yml
EOF

printf '%s\n' "${MARKER}" > "${TEST_DIR}/${MARKER}"

COMPOSE_SSH_DOCKER=(
    env "PROJECT_DIR=${TEST_DIR}"
    docker compose
    -f docker-compose.yml
    -f docker-compose.ssh.yml
    -f docker-compose.docker.yml
)

"${COMPOSE_SSH_DOCKER[@]}" run --rm --no-TTY cursor bash -lc "
set -euo pipefail
test \"\$(pwd -P)\" = \"${TEST_DIR}\"
test \"\${PROJECT_DIR}\" = \"${TEST_DIR}\"
docker info >/dev/null
docker compose version >/dev/null
cd \"${TEST_DIR}\"
docker compose -f docker-compose.yml --project-name \"${COMPOSE_PROJECT}\" run --rm --no-TTY test
"

printf 'Path parity integration test passed\n'
