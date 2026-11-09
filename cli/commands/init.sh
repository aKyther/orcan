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
                printf '  PATH:    non-interactive — connect one project from PATH (or confirm it is\n'
                printf '           already connected); useful for scripts/CI.\n'
                printf '  Saves configuration only. Run orcan sync separately to apply it.\n'
                printf '  Ownership flags belong to sync: --no-chown PATTERN / --chown-exclude /path.\n'
                printf '  Tool settings (tmux, ttyd): orcan settings (separate from this).\n'
                return 0
                ;;
            --no-chown | --chown-exclude)
                orcan_usage_error "orcan init: $1 belongs to orcan sync; run init first, then orcan sync $1 VALUE"
                return 2
                ;;
            --cli)
                cli_mode=1
                shift
                ;;
            --*) orcan_usage_error "orcan init: unknown argument: $1"; return 2 ;;
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
    mkdir -p "${ORCAN_HOME}"

    if [[ -z "${project_dir}" ]]; then
        if [[ -n "${cli_mode}" ]]; then
            ORCAN_HOME="${ORCAN_HOME}" orcan_host_python "${ORCAN_SCRIPTS}/config-wizard.py"
        else
            # Cancelling the TUI (q/Esc) exits non-zero, unlike the old wizard
            # (which always exits 0, even on "cancelled"); treat it the same
            # way here — return without applying runtime changes.
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

    ORCAN_HOME="${ORCAN_HOME}" orcan_host_python "${ORCAN_SCRIPTS}/config-show.py" || true
    orcan_ok "init done — configuration saved; runtime not applied"
    orcan_info "next: orcan sync (use --no-chown / --chown-exclude as needed; saved exclusions still apply)"
    orcan_info "  then orcan up; run orcan build first only if the image needs building"
}
