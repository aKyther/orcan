#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_init() {
    local project_dir=""
    local workspace="${WORKSPACE:-}"
    local cli_mode=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h | --help)
                printf 'usage: orcan init [PATH] [--cli]\n'
                printf '  No PATH: TUI to create/edit workspaces (default) — pick a folder,\n'
                printf '           multi-select repos, or manage what is already configured.\n'
                printf '           --cli: old sequential prompt wizard instead of the TUI.\n'
                printf '  PATH:    non-interactive — scaffold a single-project config from PATH,\n'
                printf '           for scripts/CI (skips the wizard/TUI; --cli has no effect).\n'
                printf '  Either way, finishes with orcan sync.\n'
                printf '  Tool settings (tmux, ttyd): orcan settings (separate from this).\n'
                return 0
                ;;
            --cli)
                cli_mode=1
                shift
                ;;
            *)
                if [[ -n "${project_dir}" ]]; then
                    orcan_usage_error "unexpected argument: $1"
                fi
                project_dir="$1"
                shift
                ;;
        esac
    done

    orcan_require_python
    orcan_ensure_home_env_example
    mkdir -p "${ORCAN_HOME}"

    if [[ -z "${project_dir}" ]]; then
        if [[ -n "${cli_mode}" ]]; then
            ORCAN_HOME="${ORCAN_HOME}" orcan_host_python "${ORCAN_SCRIPTS}/config-wizard.py"
        else
            # Cancelling the TUI (q/Esc) exits non-zero, unlike the old wizard
            # (which always exits 0, even on "cancelled"); treat it the same
            # way here — nothing changed, skip sync, don't fail the command.
            if ! ORCAN_HOME="${ORCAN_HOME}" ORCAN_ROOT="${ORCAN_ROOT}" ORCAN_DATA="${ORCAN_DATA:-}" \
                orcan_host_python "${ORCAN_SCRIPTS}/context_tui.py"; then
                orcan_info "cancelled — nothing changed"
                return 0
            fi
        fi
    else
        if [[ "${project_dir}" != /* ]]; then
            orcan_usage_error "path must be absolute: ${project_dir}"
        fi
        if [[ ! -d "${project_dir}" ]]; then
            orcan_die "not a directory: ${project_dir}"
        fi
        orcan_info "scaffolding workspace for ${project_dir}"
        local args=(--project-dir "${project_dir}" --config "${ORCAN_CONFIG_FILE}")
        if [[ -n "${workspace}" ]]; then
            args+=(--workspace "${workspace}")
        fi
        ORCAN_HOME="${ORCAN_HOME}" orcan_host_python \
            "${ORCAN_SCRIPTS}/config-scaffold.py" "${args[@]}"
    fi

    # shellcheck source=sync.sh
    source "$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sync.sh"
    orcan_cmd_sync
    ORCAN_HOME="${ORCAN_HOME}" orcan_host_python "${ORCAN_SCRIPTS}/config-show.py" || true
    orcan_ok "init done"
    orcan_info "next: orcan build && orcan up"
}
