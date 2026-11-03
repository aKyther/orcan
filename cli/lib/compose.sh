#!/usr/bin/env bash
# Docker Compose wrappers — files from ORCAN_ROOT, settings/overlays from ORCAN_HOME.
# shellcheck shell=bash

# $1 env-var override, $2 basename under ORCAN_RUNTIME_DIR when it is unset.
_orcan_compose_file() {
    local override="${1:-}"
    if [[ -n "${override}" ]]; then
        printf '%s\n' "${override}"
    else
        printf '%s\n' "${ORCAN_RUNTIME_DIR}/${2}"
    fi
}

orcan_compose_projects_file() {
    _orcan_compose_file "${ORCAN_COMPOSE_PROJECTS:-}" compose-projects.generated.yml
}

orcan_compose_git_file() {
    _orcan_compose_file "${ORCAN_COMPOSE_GIT:-}" compose-git.generated.yml
}

orcan_compose_github_file() {
    _orcan_compose_file "${ORCAN_COMPOSE_GITHUB:-}" compose-github.generated.yml
}

orcan_compose_gitlab_file() {
    _orcan_compose_file "${ORCAN_COMPOSE_GITLAB:-}" compose-gitlab.generated.yml
}

orcan_compose_network_file() {
    _orcan_compose_file "${ORCAN_COMPOSE_NETWORK:-}" compose-network.generated.yml
}

# Fill nameref array with -f <file> for project mounts (+ optional git overlay).
# Pass with_git=1 as second arg to include compose-git.generated.yml.
orcan_compose_overlay_args() {
    local -n _out="$1"
    local with_git="${2:-0}"
    local projects gitf
    _out=()
    projects="$(orcan_compose_projects_file)"
    _out+=(-f "${projects}")
    if (( with_git )); then
        gitf="$(orcan_compose_git_file)"
        if [[ ! -f "${gitf}" ]]; then
            orcan_die "git overlay missing: ${gitf} (run: orcan up --with-ssh)"
        fi
        _out+=(-f "${gitf}")
    fi
}

# Default project stays "orcan"; --instance selects its own named project.
orcan_compose_project_args() {
    local -n _out="$1"
    _out=(--project-name "${COMPOSE_PROJECT_NAME:-orcan}")
}

orcan_compose_base() {
    orcan_load_config
    local overlays=() project=()
    orcan_compose_overlay_args overlays 0
    orcan_compose_project_args project
    docker compose \
        "${project[@]}" \
        --env-file /dev/null \
        --project-directory "${ORCAN_ROOT}" \
        -f "${ORCAN_ROOT}/docker-compose.yml" \
        "${overlays[@]}" \
        "$@"
}

orcan_compose_build() {
    orcan_load_config
    local project=()
    orcan_compose_project_args project
    docker compose \
        "${project[@]}" \
        --env-file /dev/null \
        --project-directory "${ORCAN_ROOT}" \
        -f "${ORCAN_ROOT}/docker-compose.yml" \
        "$@"
}

orcan_up_state_file() {
    printf '%s\n' "${ORCAN_RUNTIME_DIR}/up-state.json"
}

# Persist the last `orcan up` overlay combo so down/logs can reuse it.
orcan_write_up_state() {
    local with_docker="${1:-0}"
    local with_git="${2:-0}"
    local with_network="${3:-0}"
    local with_ttyd="${4:-0}"
    local network_name="${5:-}"
    local statef
    statef="$(orcan_up_state_file)"
    mkdir -p "$(dirname "${statef}")"
    orcan_host_python "${ORCAN_SCRIPTS}/runtime-settings.py" --state-write "${statef}" \
        "WITH_DOCKER=${with_docker}" "WITH_GIT=${with_git}" \
        "WITH_NETWORK=${with_network}" "WITH_TTYD=${with_ttyd}" \
        "NETWORK_NAME=${network_name}" "WITH_GITHUB=${6:-0}" \
        "GITHUB_HOSTNAME=${7:-}" "WITH_GITLAB=${8:-0}" \
        "GITLAB_HOSTNAME=${9:-}" "WITH_REDIS=${10:-0}"

}

# Last requested `orcan up` flags; unlike up-state.json, `orcan down` keeps it
# so `orcan up --resume` can restore the same stack. Never stores credentials.
orcan_last_up_file() {
    printf '%s\n' "${ORCAN_RUNTIME_DIR}/last-up.json"
}

orcan_write_last_up() {
    local statef
    statef="$(orcan_last_up_file)"
    mkdir -p "$(dirname "${statef}")"
    orcan_host_python "${ORCAN_SCRIPTS}/runtime-settings.py" --state-write "${statef}" \
        "WITH_DOCKER=${1:-0}" "WITH_GIT=${2:-0}" "WITH_NETWORK=${3:-0}" \
        "WITH_TTYD=${4:-0}" "WITH_TTYD_AUTH=${5:-0}" "NETWORK_NAME=${6:-}" \
        "WITH_GITHUB=${7:-0}" "GITHUB_HOSTNAME=${8:-}" "WITH_GITLAB=${9:-0}" \
        "GITLAB_HOSTNAME=${10:-}" "WITH_REDIS=${11:-0}"

}

orcan_load_up_state() {
    local statef
    statef="$(orcan_up_state_file)"
    [[ -f "${statef}" ]] || return 1
    local exports
    exports="$(orcan_host_python "${ORCAN_SCRIPTS}/runtime-settings.py" --state-read "${statef}")" || return
    eval "${exports}"
    return 0
}

orcan_clear_up_state() {
    rm -f "$(orcan_up_state_file)"
}

orcan_container_name() {
    printf 'orcan-%s\n' "${ORCAN_INSTANCE:-1}"
}

# Print the running container name or exit with a helpful message.
orcan_require_running_container() {
    orcan_require_docker
    orcan_load_config
    local name
    name="$(orcan_container_name)"
    if ! docker ps -q -f "name=^${name}$" 2>/dev/null | grep -q .; then
        orcan_die "no running container — start with: orcan up   (local: orcan enter; remote browser: orcan up --web-terminal)"
    fi
    printf '%s\n' "${name}"
}

# Compose stack for `orcan up`: optional docker socket, git/SSH, network join, ttyd.
# Usage: orcan_compose_up_run <docker> <git> <network> <ttyd> <github> <gitlab> -- compose args...
orcan_compose_up_run() {
    orcan_load_config
    local with_docker="${1:-0}"
    local with_git="${2:-0}"
    local with_network="${3:-0}"
    local with_ttyd="${4:-0}"
    local with_github="${5:-0}"
    local with_gitlab="${6:-0}"
    shift 6
    local overlays=() project=()
    orcan_compose_overlay_args overlays "${with_git}"
    orcan_compose_project_args project
    local -a cmd=(
        docker compose
        "${project[@]}"
        --env-file /dev/null
        --project-directory "${ORCAN_ROOT}"
        -f "${ORCAN_ROOT}/docker-compose.yml"
        "${overlays[@]}"
    )
    if (( with_ttyd )); then
        cmd+=(-f "${ORCAN_ROOT}/plugins/ttyd/compose.yml")
    else
        cmd+=(-f "${ORCAN_ROOT}/docker-compose.keepalive.yml")
    fi
    if (( with_docker )); then
        cmd+=(-f "${ORCAN_ROOT}/plugins/docker/compose.yml")
    fi
    if (( with_network )); then
        cmd+=(-f "$(orcan_compose_network_file)")
    fi
    if ((with_github)); then
        cmd+=(-f "$(orcan_compose_github_file)")
    fi
    if ((with_gitlab)); then
        cmd+=(-f "$(orcan_compose_gitlab_file)")
    fi
    if [[ "${ORCAN_REDIS_ENABLED:-0}" == "1" ]]; then
        cmd+=(-f "${ORCAN_ROOT}/plugins/redis/compose.yml")
    fi
    "${cmd[@]}" "$@"
}

# Tear down every previously-possible up.sh overlay combo so leftover volume
# mounts from a prior `orcan up` never linger under a mismatched container.
orcan_compose_ttyd_down_all_variants() {
    local git_variants=(0) network_variants=(0)
    [[ -f "$(orcan_compose_git_file)" ]] && git_variants+=(1)
    [[ -f "$(orcan_compose_network_file)" ]] && network_variants+=(1)
    local d g n t
    for t in 0 1; do
        for d in 0 1; do
            for g in "${git_variants[@]}"; do
                for n in "${network_variants[@]}"; do
                    orcan_compose_up_run "${d}" "${g}" "${n}" "${t}" 0 0 down --remove-orphans > /dev/null 2>&1 || true
                done
            done
        done
    done
    orcan_clear_up_state
}

orcan_require_generated() {
    ORCAN_HOME="${ORCAN_HOME}" ORCAN_ROOT="${ORCAN_ROOT}" \
        "${ORCAN_SCRIPTS}/require-generated.sh"
}

# Compatibility helpers remain callable by host tools; package files only define functions.
for _orcan_plugin in github gitlab ssh network; do
    # shellcheck disable=SC1090
    source "${ORCAN_ROOT:-$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}/plugins/${_orcan_plugin}/runtime.sh"
done
unset _orcan_plugin
