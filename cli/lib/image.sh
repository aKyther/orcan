#!/usr/bin/env bash
# Image pull / build / publish helpers (manual registry; CI does not publish).
#
# Tags:
#   both agents → orcan:latest + orcan:<VERSION>   (registry)
#   --claude    → orcan:<VERSION>-claude           (local only)
#   --cursor    → orcan:<VERSION>-cursor           (local only)
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

# Local docker tag for an agent selection.
orcan_image_tag_for() {
    local variant="${1:-full}"
    local ver
    ver="$(orcan_image_version)"
    case "${variant}" in
        full) printf 'orcan:%s\n' "${ver}" ;;
        claude) printf 'orcan:%s-claude\n' "${ver}" ;;
        cursor) printf 'orcan:%s-cursor\n' "${ver}" ;;
        *) orcan_die "unknown agent selection: ${variant}" ;;
    esac
}

orcan_image_compose_name_for() {
    local variant="${1:-full}"
    case "${variant}" in
        full) printf '%s\n' "${IMAGE_LOCAL:-orcan:latest}" ;;
        claude | cursor) orcan_image_tag_for "${variant}" ;;
        *) orcan_die "unknown agent selection: ${variant}" ;;
    esac
}

# Pull both-agents orcan:<VERSION> → orcan:latest + orcan:<VERSION>.
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
    # Strip accidental agent suffixes from IMAGE_TAG for registry pull.
    tag="${tag%-claude}"
    tag="${tag%-cursor}"
    local_image="${IMAGE_LOCAL:-orcan:latest}"
    remote="$(orcan_image_remote "${tag}")"

    orcan_info "trying pull ${remote}"
    if ! docker pull "${remote}"; then
        orcan_warn "pull failed: ${remote}"
        return 1
    fi

    docker tag "${remote}" "${local_image}"
    docker tag "${local_image}" "orcan:${ver}" 2>/dev/null || true
    orcan_ok "using registry image as ${local_image} (also orcan:${ver})"
    return 0
}

# agents: full | claude | cursor
orcan_image_build_local() {
    local variant="${1:-full}"
    local no_cache="${2:-0}"
    local ver build_args image versioned install_cursor install_claude

    ver="$(orcan_image_version)"
    versioned="$(orcan_image_tag_for "${variant}")"
    build_args=(build)
    if (( no_cache )); then
        build_args+=(--no-cache)
    fi

    case "${variant}" in
        full)
            install_cursor=1
            install_claude=1
            image="$(orcan_image_compose_name_for full)"
            orcan_info "building ${image} + ${versioned} (Claude Code + Cursor CLI)"
            ;;
        claude)
            install_cursor=0
            install_claude=1
            image="${versioned}"
            orcan_info "building ${image} (Claude Code only — Cursor not installed; no pull)"
            ;;
        cursor)
            install_cursor=1
            install_claude=0
            image="${versioned}"
            orcan_info "building ${image} (Cursor CLI only — Claude not installed; no pull)"
            ;;
        *)
            orcan_die "unknown agent selection: ${variant}"
            ;;
    esac

    ORCAN_VERSION="${ver}" IMAGE_LOCAL="${image}" \
        INSTALL_CURSOR="${install_cursor}" INSTALL_CLAUDE="${install_claude}" \
        orcan_compose_build "${build_args[@]}"

    if [[ "${variant}" == "full" ]]; then
        docker tag "${image}" "${versioned}" 2>/dev/null || true
        docker tag "${image}" orcan:latest 2>/dev/null || true
        orcan_ok "built ${image} / ${versioned} (both agents)"
    else
        orcan_ok "built ${image}"
        orcan_info "run with: IMAGE_LOCAL=${image} orcan up"
        orcan_info "or set IMAGE_LOCAL=${image} in ${ORCAN_ENV_FILE:-.env}"
    fi
}

orcan_image_variant_of() {
    local image="$1"
    docker run --rm --entrypoint cat "${image}" /etc/orcan/variant 2>/dev/null | tr -d '[:space:]' || true
}

# Push both-agents orcan:latest (or orcan:VERSION) to registry.
orcan_image_publish() {
    local local_image remote tag ver variant versioned

    if ! orcan_image_registry_configured; then
        orcan_die "set IMAGE_REPOSITORY (and optional IMAGE_REGISTRY) in ${ORCAN_ENV_FILE:-.env}"
    fi

    orcan_image_load_registry_env
    ver="$(orcan_image_version)"
    tag="${IMAGE_TAG%-claude}"
    tag="${tag%-cursor}"
    versioned="orcan:${ver}"
    local_image="orcan:latest"
    if ! docker image inspect "${local_image}" >/dev/null 2>&1; then
        local_image="${versioned}"
    fi
    if ! docker image inspect "${local_image}" >/dev/null 2>&1; then
        orcan_die "local both-agents image missing — run: orcan build --force"
    fi

    variant="$(orcan_image_variant_of "${local_image}")"
    if [[ -n "${variant}" && "${variant}" != "full" ]]; then
        orcan_die "refusing to publish agents=${variant} — publish only orcan:latest / orcan:<VERSION> (both agents)"
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
