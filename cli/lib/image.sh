#!/usr/bin/env bash
# Image pull / build / publish helpers (manual registry; CI does not publish).
#
# Every build uses the standard local tags. Its installed clients are recorded
# in /etc/orcan/agents.json; that manifest, not a tag suffix, is the contract.
#
# shellcheck shell=bash

orcan_image_version() {
    tr -d '[:space:]' < "${ORCAN_ROOT}/VERSION" 2>/dev/null || printf 'dev'
}

orcan_image_load_registry_env() {
    orcan_load_env
    IMAGE_REGISTRY="${IMAGE_REGISTRY:-ghcr.io}"
    IMAGE_REPOSITORY="${IMAGE_REPOSITORY:-akyther/orcan}"
    if [[ -z "${IMAGE_TAG:-}" ]]; then
        IMAGE_TAG="$(orcan_image_version)"
    fi
    IMAGE_LOCAL="${IMAGE_LOCAL:-orcan:latest}"
    export IMAGE_REGISTRY IMAGE_REPOSITORY IMAGE_TAG IMAGE_LOCAL
}

orcan_image_remote() {
    local tag="${1:-${IMAGE_TAG}}"
    printf '%s/%s:%s\n' "${IMAGE_REGISTRY}" "${IMAGE_REPOSITORY}" "${tag}"
}

orcan_image_registry_configured() {
    orcan_image_load_registry_env
    [[ -n "${IMAGE_REPOSITORY:-}" && -n "${IMAGE_REGISTRY:-}" ]]
}

# Read the baked agent selection without starting the image's entrypoint.
orcan_image_agents_manifest() {
    local image="$1"
    docker run --rm --entrypoint cat "${image}" /etc/orcan/agents.json 2>/dev/null || true
}

# A registry image is a portable baseline only when it contains every client.
orcan_image_has_all_agents() {
    local image="$1" manifest
    manifest="$(orcan_image_agents_manifest "${image}")"
    [[ -n "${manifest}" ]] || return 1
    python3 -c '
import json, sys
try:
    agents = json.load(sys.stdin)["agents"]
except (json.JSONDecodeError, KeyError, TypeError):
    raise SystemExit(1)
raise SystemExit(not all(agents.get(name) is True for name in ("cursor", "claude", "codex", "gemini", "copilot")))
' <<<"${manifest}"
}

# Pull the portable all-agents registry image → orcan:latest + orcan:<VERSION>.
orcan_image_try_pull() {
    local local_image remote tag ver

    orcan_image_load_registry_env
    ver="$(orcan_image_version)"
    if [[ "${ver}" == "dev" ]]; then
        orcan_warn "VERSION is 'dev' — skipping registry pull"
        return 1
    fi

    if ! orcan_image_registry_configured; then
        orcan_warn "registry not configured — skipping pull"
        return 1
    fi

    tag="${IMAGE_TAG}"
    local_image="${IMAGE_LOCAL:-orcan:latest}"
    remote="$(orcan_image_remote "${tag}")"

    orcan_info "trying pull ${remote}"
    if ! docker pull "${remote}"; then
        orcan_warn "pull failed: ${remote}"
        return 1
    fi

    if ! orcan_image_has_all_agents "${remote}"; then
        orcan_warn "registry image is missing the all-agents manifest: ${remote}"
        return 1
    fi

    docker tag "${remote}" "${local_image}"
    docker tag "${local_image}" "orcan:${ver}" 2>/dev/null || true
    orcan_ok "using registry image as ${local_image} (also orcan:${ver})"
    return 0
}

# agents: '+'-joined cursor | claude | codex | gemini | copilot
orcan_image_build_local() {
    local agents="$1"
    local no_cache="${2:-0}"
    local ver build_args image install_cursor=0 install_claude=0 install_codex=0 install_gemini=0 install_copilot=0 agent

    ver="$(orcan_image_version)"
    image="${IMAGE_LOCAL:-orcan:latest}"
    build_args=(build)
    if (( no_cache )); then
        build_args+=(--no-cache)
    fi

    IFS='+' read -r -a selected_agents <<<"${agents}"
    for agent in "${selected_agents[@]}"; do
        case "${agent}" in
            cursor) install_cursor=1 ;; claude) install_claude=1 ;; codex) install_codex=1 ;;
            gemini) install_gemini=1 ;; copilot) install_copilot=1 ;;
            *) orcan_die "unknown agent selection: ${agent}" ;;
        esac
    done
    orcan_info "building ${image} (agents: ${agents})"

    ORCAN_VERSION="${ver}" IMAGE_LOCAL="${image}" \
        INSTALL_CURSOR="${install_cursor}" INSTALL_CLAUDE="${install_claude}" \
        INSTALL_CODEX="${install_codex}" INSTALL_GEMINI="${install_gemini}" INSTALL_COPILOT="${install_copilot}" \
        orcan_compose_build "${build_args[@]}"
    docker tag "${image}" "orcan:${ver}" 2>/dev/null || true
    docker tag "${image}" orcan:latest 2>/dev/null || true
    orcan_ok "built ${image} (manifest: /etc/orcan/agents.json)"
}

# Push the all-agents local image (orcan:latest / orcan:VERSION) to registry.
orcan_image_publish() {
    local local_image remote tag ver versioned

    if ! orcan_image_registry_configured; then
        orcan_die "set IMAGE_REPOSITORY (and optional IMAGE_REGISTRY) in ${ORCAN_ENV_FILE:-.env}"
    fi

    orcan_image_load_registry_env
    ver="$(orcan_image_version)"
    versioned="orcan:${ver}"
    local_image="orcan:latest"
    if ! docker image inspect "${local_image}" >/dev/null 2>&1; then
        local_image="${versioned}"
    fi
    if ! docker image inspect "${local_image}" >/dev/null 2>&1; then
        orcan_die "local all-agents image missing — run: orcan build --all-agents --force"
    fi

    if ! orcan_image_has_all_agents "${local_image}"; then
        orcan_die "refusing to publish a partial or legacy image — rebuild with: orcan build --all-agents"
    fi

    remote="$(orcan_image_remote "${tag}")"
    orcan_info "publishing ${local_image} → ${remote}"
    docker tag "${local_image}" "${remote}"
    docker push "${remote}"
    local latest_remote
    latest_remote="$(orcan_image_remote latest)"
    docker tag "${local_image}" "${latest_remote}"
    docker push "${latest_remote}" || orcan_warn "could not push :latest (version tag is published)"
    orcan_ok "published ${remote}"
}
