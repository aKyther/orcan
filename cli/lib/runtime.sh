#!/usr/bin/env bash
# Runtime / .env / generated-files checks and user-facing hints.
# shellcheck shell=bash

orcan_runtime_compose_mounts_file() {
    orcan_load_env 2>/dev/null || true
    printf '%s\n' "${ORCAN_COMPOSE_PROJECTS:-${ORCAN_RUNTIME_DIR}/compose-projects.generated.yml}"
}

orcan_runtime_config_json_file() {
    orcan_load_env 2>/dev/null || true
    printf '%s\n' "${ORCAN_CONFIG_HOST:-${ORCAN_RUNTIME_DIR}/runtime-config.json}"
}

orcan_runtime_config_is_stale() {
    local config_file compose_file runtime_file
    config_file="$(orcan_config_path 2>/dev/null)" || return 1
    compose_file="$(orcan_runtime_compose_mounts_file)"
    runtime_file="$(orcan_runtime_config_json_file)"
    [[ -f "${runtime_file}" && -f "${compose_file}" ]] || return 1
    [[ "${config_file}" -nt "${runtime_file}" || "${config_file}" -nt "${compose_file}" ]]
}

# orcan build: needs .env (UID/GID, registry vars). Does not need mounts/*.
orcan_require_env_for_build() {
    if [[ -f "${ORCAN_ENV_FILE}" ]]; then
        return 0
    fi
    orcan_error ".env not found: ${ORCAN_ENV_FILE}"
    orcan_error "orcan build needs .env (host UID/GID for the image)."
    if [[ -f "${ORCAN_CONFIG_FILE}" ]]; then
        orcan_error "Fix:  orcan sync"
    else
        orcan_error "Fix:  orcan init /absolute/path/to/repo"
    fi
    orcan_error "Note: orcan up also needs mounts/* — always run orcan sync after editing orcan.config.json."
    exit 1
}

# Warn after build when config drift would break the next orcan up.
orcan_runtime_warn_if_config_stale() {
    local context="${1:-build}"
    if ! orcan_runtime_config_is_stale; then
        return 0
    fi
    case "${context}" in
        build)
            orcan_warn "orcan.config.json is newer than mounts/* — run orcan sync before orcan up"
            orcan_warn "  (build can continue; workspace changes do not require a rebuild)"
            ;;
        *)
            orcan_warn "orcan.config.json is newer than generated runtime — run: orcan sync"
            ;;
    esac
}

# Read one TTYD_* value from .env, falling back to $2 when unset.
_orcan_ttyd_env() {
    orcan_load_env 2>/dev/null || true
    printf '%s\n' "${!1:-$2}"
}

orcan_ttyd_bind() {
    _orcan_ttyd_env TTYD_BIND 0.0.0.0
}

orcan_ttyd_host_port() {
    _orcan_ttyd_env TTYD_HOST_PORT 7681
}

orcan_ttyd_container_port() {
    _orcan_ttyd_env TTYD_PORT 7681
}

# Same URL shape as `orcan url` and `orcan up --with-ttyd` success line.
# A wildcard bind (0.0.0.0 / ::) isn't itself a dialable address — printing
# it literally gives an unusable URL. `localhost` at least works from this
# same host; reaching it from elsewhere (LAN/Tailscale) needs the host's own
# address, which this helper has no reliable way to know.
orcan_terminal_url() {
    local bind
    bind="$(orcan_ttyd_bind)"
    case "${bind}" in
        0.0.0.0 | :: | "[::]") bind="localhost" ;;
    esac
    printf 'http://%s:%s\n' "${bind}" "$(orcan_ttyd_host_port)"
}

orcan_container_is_running() {
    local name="${1:-}"
    orcan_load_env 2>/dev/null || true
    [[ -n "${name}" ]] || name="$(orcan_container_name)"
    orcan_have docker || return 1
    docker ps -q -f "name=^${name}$" 2>/dev/null | grep -q .
}

# True when the last up (or a legacy stack) published the ttyd port.
orcan_ttyd_is_active() {
    local cname container_port
    if orcan_load_up_state && [[ "${WITH_TTYD:-0}" == "1" ]]; then
        return 0
    fi
    orcan_load_env 2>/dev/null || true
    cname="$(orcan_container_name)"
    orcan_container_is_running "${cname}" || return 1
    container_port="$(orcan_ttyd_container_port)"
    docker port "${cname}" "${container_port}/tcp" 2>/dev/null | grep -q .
}

orcan_require_ttyd_for_url() {
    if orcan_ttyd_is_active; then
        return 0
    fi
    if orcan_container_is_running; then
        orcan_die "browser terminal is off — orcan down && orcan up --with-ttyd   (local: orcan enter)"
    fi
    orcan_die "no running container — start with: orcan up --with-ttyd   (or plain orcan up for local: orcan enter)"
}

# Human-readable summary of mounts/up-state.env for doctor / logs.
orcan_up_state_summary() {
    local parts=()
    if ! orcan_load_up_state; then
        printf 'unknown (no up-state.env)\n'
        return 0
    fi
    if [[ "${WITH_TTYD:-0}" == "1" ]]; then
        parts+=("ttyd")
    else
        parts+=("local-only")
    fi
    if [[ "${WITH_DOCKER:-0}" == "1" ]]; then
        parts+=("docker-socket")
    fi
    if [[ "${WITH_GIT:-0}" == "1" ]]; then
        parts+=("git/ssh")
    fi
    if [[ "${WITH_NETWORK:-0}" == "1" && -n "${NETWORK_NAME:-}" ]]; then
        parts+=("network:${NETWORK_NAME}")
    fi
    local IFS=', '
    printf '%s\n' "${parts[*]}"
}
