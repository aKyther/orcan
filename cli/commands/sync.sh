#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_sync() {
    local prune_orphans=0
    local arg
    local -a rest=()

    while [[ $# -gt 0 ]]; do
        arg="$1"
        shift
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

    orcan_sync_reconcile_host
    orcan_sync_reconcile_running_container "${prune_orphans}"

    orcan_ok "sync complete"
    orcan_info "next: orcan up   (skip if live reconcile already applied changes)"
    orcan_info "  orcan build only when the image, Dockerfile, or agent install set changed"
}

# Host-side reconcile: $ORCAN_HOME/workspaces/<name>/ symlinks are written here
# (meta_path), bind-mounted as /home/developer/workspaces/<name>/ in the
# container. Runs even when the container is down.
orcan_sync_reconcile_host() {
    orcan_info "reconciling workspace meta on host"
    local host_out
    host_out="$(ORCAN_HOME="${ORCAN_HOME}" ORCAN_ROOT="${ORCAN_ROOT}" \
        orcan_host_python "${ORCAN_SCRIPTS}/reconcile-host.py" 2>&1)" || {
        orcan_warn "host workspace reconcile failed"
        return 0
    }
    printf '%s\n' "${host_out}"
    orcan_sync_reconcile_report_warnings "${host_out}" 0
    orcan_ok "host workspace reconcile complete"
}

orcan_sync_reconcile_report_warnings() {
    local reconcile_out="$1"
    local in_container="${2:-0}"
    if grep -q 'skip missing repo mount' <<<"${reconcile_out}"; then
        if [[ "${in_container}" == "1" ]]; then
            orcan_warn "some project paths are not visible in the container — run: orcan down && orcan up"
        else
            orcan_warn "some project paths are not visible on this machine — check paths and mounts"
        fi
    fi
    if grep -q 'replaced real directory with backup' <<<"${reconcile_out}"; then
        orcan_info "relocated stale checkout dirs that blocked symlinks (see *.orcan-reconcile-bak)"
    fi
    if grep -q 'skip: could not relocate blocking directory' <<<"${reconcile_out}"; then
        orcan_warn "reconcile could not fix every blocking directory — check logs above"
    fi
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
        orcan_info "container not running — host workspace meta reconciled; run orcan up for tmux/runtime"
        return 0
    fi
    orcan_info "container is running — reconciling live (no restart)"
    local -a reconcile_cmd=(orcan-runtime-reconcile)
    if [[ "${prune_orphans}" == "1" ]]; then
        reconcile_cmd+=(--prune-orphans)
    fi
    local reconcile_out
    reconcile_out="$(docker exec -i "${cname}" "${reconcile_cmd[@]}" 2>&1)" || {
        orcan_warn "live reconcile failed — falling back to: orcan down && orcan up"
        return 0
    }
    printf '%s\n' "${reconcile_out}"
    orcan_sync_reconcile_report_warnings "${reconcile_out}" 1
    orcan_ok "live reconcile complete"
}
