#!/usr/bin/env bash
# Docker Compose wrappers — files from ORCAN_ROOT, env/overlays from ORCAN_HOME.
# shellcheck shell=bash

orcan_compose_projects_file() {
    local from_env
    from_env="${ORCAN_COMPOSE_PROJECTS:-}"
    if [[ -n "${from_env}" ]]; then
        printf '%s\n' "${from_env}"
        return 0
    fi
    printf '%s\n' "${ORCAN_RUNTIME_DIR}/compose-projects.generated.yml"
}

orcan_compose_base() {
    local projects
    projects="$(orcan_compose_projects_file)"
    docker compose \
        --env-file "${ORCAN_ENV_FILE}" \
        --project-directory "${ORCAN_ROOT}" \
        -f "${ORCAN_ROOT}/docker-compose.yml" \
        -f "${projects}" \
        "$@"
}

orcan_compose_build() {
    docker compose \
        --env-file "${ORCAN_ENV_FILE}" \
        --project-directory "${ORCAN_ROOT}" \
        -f "${ORCAN_ROOT}/docker-compose.yml" \
        "$@"
}

orcan_compose_ttyd() {
    local projects
    projects="$(orcan_compose_projects_file)"
    docker compose \
        --env-file "${ORCAN_ENV_FILE}" \
        --project-directory "${ORCAN_ROOT}" \
        -f "${ORCAN_ROOT}/docker-compose.yml" \
        -f "${projects}" \
        -f "${ORCAN_ROOT}/docker-compose.ttyd.yml" \
        "$@"
}

orcan_compose_ttyd_docker() {
    local projects
    projects="$(orcan_compose_projects_file)"
    docker compose \
        --env-file "${ORCAN_ENV_FILE}" \
        --project-directory "${ORCAN_ROOT}" \
        -f "${ORCAN_ROOT}/docker-compose.yml" \
        -f "${projects}" \
        -f "${ORCAN_ROOT}/docker-compose.ttyd.yml" \
        -f "${ORCAN_ROOT}/docker-compose.docker.yml" \
        "$@"
}

orcan_require_generated() {
    ORCAN_HOME="${ORCAN_HOME}" ORCAN_ROOT="${ORCAN_ROOT}" \
        "${ORCAN_SCRIPTS}/require-generated.sh"
}
