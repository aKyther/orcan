#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_uninstall() {
    local purge=0
    local purge_images=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --purge-data)
                purge=1
                shift
                ;;
            --purge-images)
                purge_images=1
                shift
                ;;
            -h | --help)
                printf 'usage: orcan uninstall [--purge-data] [--purge-images]\n'
                printf '  Removes ~/.local/bin/orcan and the install under ORCAN_ROOT.\n'
                printf '  --purge-data deletes config/logins/caches but always preserves ORCAN_PROJECTS_ROOT.\n'
                printf '  --purge-images removes local Docker tags matching orcan:*.\n'
                return 0
                ;;
            *)
                orcan_usage_error "unknown argument: $1"
                ;;
        esac
    done

    local launcher="${HOME}/.local/bin/orcan"
    local share_default="${XDG_DATA_HOME:-${HOME}/.local/share}/orcan"

    # Resolve generated ORCAN_DATA / ORCAN_PROJECTS_ROOT before deleting the
    # install clone or config that contains .env.
    orcan_load_env 2>/dev/null || true
    local data="${ORCAN_DATA:-${XDG_CONFIG_HOME:-${HOME}/.config}/orcan}"
    local projects_root="${ORCAN_PROJECTS_ROOT:-${data}/sandbox}"

    orcan_warn "This removes the orcan CLI launcher and install clone."
    if (( purge )); then
        orcan_warn "Config/data will be purged: ORCAN_HOME=${ORCAN_HOME}, ORCAN_DATA=${data}"
        orcan_warn "Project checkouts are always preserved: ORCAN_PROJECTS_ROOT=${projects_root}"
    else
        orcan_warn "Config/data and projects are kept."
    fi
    if (( purge_images )); then
        orcan_warn "Local Docker tags matching orcan:* will be removed where possible."
    fi
    printf 'Type yes to continue: '
    local answer=""
    read -r answer || true
    if [[ "${answer}" != "yes" ]]; then
        orcan_info "aborted"
        return 1
    fi

    if orcan_have docker; then
        orcan_info "stopping containers (all up overlay variants)"
        orcan_compose_ttyd_down_all_variants
    fi

    if [[ -L "${launcher}" || -f "${launcher}" ]]; then
        rm -f -- "${launcher}"
        orcan_info "removed ${launcher}"
    fi

    if (( purge )); then
        orcan_require_python
        if orcan_host_python "${ORCAN_SCRIPTS}/uninstall_data.py" \
            --target "${ORCAN_HOME}" \
            --target "${data}" \
            --protect "${projects_root}" \
            --protect "${ORCAN_ROOT}" \
            --config "${ORCAN_CONFIG_FILE}"; then
            orcan_ok "purged Orcan config/data; preserved ${projects_root}"
        else
            orcan_die "data purge stopped by path safety checks"
        fi
    fi

    if (( purge_images )); then
        if ! orcan_have docker; then
            orcan_warn "docker not found — images were not removed"
        else
            local -a images=()
            mapfile -t images < <(
                docker image ls --filter 'reference=orcan:*' \
                    --format '{{.Repository}}:{{.Tag}}' 2>/dev/null | sort -u
            )
            if (( ${#images[@]} == 0 )); then
                orcan_info "no local orcan:* image tags found"
            elif docker image rm "${images[@]}"; then
                orcan_ok "removed local orcan:* image tags"
            else
                orcan_warn "some orcan:* images are still used by another container and were kept"
            fi
        fi
    fi

    # Delete the installed source last: --purge-data still needs its Python
    # helper. Never delete an arbitrary development checkout.
    if [[ "${ORCAN_ROOT}" == "${share_default}" || "${ORCAN_ROOT}" == "${HOME}/.orcan" ]]; then
        rm -rf -- "${ORCAN_ROOT}"
        orcan_info "removed ${ORCAN_ROOT}"
    else
        orcan_warn "leaving ORCAN_ROOT in place (dev checkout?): ${ORCAN_ROOT}"
        orcan_warn "delete manually if desired"
    fi

    orcan_ok "uninstall finished"
}
