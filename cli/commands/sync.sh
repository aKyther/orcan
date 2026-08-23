#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_sync() {
    local prune_orphans=0
    local arg
    for arg in "$@"; do
        case "${arg}" in
            --prune-orphans) prune_orphans=1 ;;
            *) orcan_usage_error "orcan sync: unknown argument: ${arg}" ;;
        esac
    done

    orcan_require_python
    orcan_ensure_home_env_example
    mkdir -p "${ORCAN_HOME}" "${ORCAN_RUNTIME_DIR}"

    local cfg=""
    if cfg="$(orcan_config_path)"; then
        :
    else
        cfg=""
    fi

    orcan_info "syncing config → ${ORCAN_HOME}"
    CONFIG="${cfg}" \
        PROJECT_DIR="${PROJECT_DIR:-${ORCAN_HOME}}" \
        ORCAN_HOME="${ORCAN_HOME}" \
        ORCAN_ROOT="${ORCAN_ROOT}" \
        "${ORCAN_SCRIPTS}/update-env.sh"

    orcan_info "compiling context assertions → workspace context packs"
    ORCAN_DATA="${ORCAN_DATA:-${HOME}/.config/orcan}" \
        orcan_host_python "${ORCAN_SCRIPTS}/compile_context.py" "${ORCAN_HOME}"

    orcan_sync_reconcile_running_container "${prune_orphans}"

    orcan_ok "sync complete"
    orcan_info "next: orcan up   (skip if live reconcile already applied changes)"
    orcan_info "  orcan build only when the image, Dockerfile, or agent install set changed"
}

# If a container is already running, push the freshly-synced desired state
# into it immediately (same reconcile mechanism container boot uses) instead
# of telling the user to `orcan down && orcan up`. A brand-new project path
# outside the managed root still needs a recreate to get its own bind mount
# (docker compose up -d would pick that up on its own next run) — this only
# covers the common case: everything already visible under an existing
# mount (managed root, workspaces parent, or single-file runtime-config.json)
# becomes live without touching the container at all.
orcan_sync_reconcile_running_container() {
    local prune_orphans="${1:-0}"
    local cname
    if ! orcan_require_docker 2>/dev/null; then
        return 0
    fi
    orcan_load_env
    cname="$(orcan_container_name)"
    if ! docker ps -q -f "name=^${cname}$" 2>/dev/null | grep -q .; then
        return 0
    fi
    orcan_info "container is running — reconciling live (no restart)"
    local -a reconcile_cmd=(orcan-runtime-reconcile)
    if [[ "${prune_orphans}" == "1" ]]; then
        reconcile_cmd+=(--prune-orphans)
    fi
    if docker exec -i "${cname}" "${reconcile_cmd[@]}"; then
        orcan_ok "live reconcile complete"
    else
        orcan_warn "live reconcile failed — falling back to: orcan down && orcan up"
    fi
}
