#!/usr/bin/env bash
# shellcheck shell=bash

orcan_cmd_uninstall() {
    local purge=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --purge-data)
                purge=1
                shift
                ;;
            -h | --help)
                printf 'usage: orcan uninstall [--purge-data]\n'
                printf '  Removes ~/.local/bin/orcan and the install under ORCAN_ROOT.\n'
                printf '  --purge-data also deletes ORCAN_DATA (logins/caches) after confirmation.\n'
                return 0
                ;;
            *)
                orcan_usage_error "unknown argument: $1"
                ;;
        esac
    done

    local launcher="${HOME}/.local/bin/orcan"
    local share_default="${XDG_DATA_HOME:-${HOME}/.local/share}/orcan"

    orcan_warn "This removes the orcan CLI launcher and install clone."
    orcan_warn "ORCAN_HOME config (${ORCAN_HOME}) is kept unless you delete it yourself."
    if (( purge )); then
        orcan_warn "ORCAN_DATA (${ORCAN_DATA}) will be deleted after confirmation."
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

    # Only delete ORCAN_ROOT if it looks like the XDG install (not a random dev checkout).
    if [[ "${ORCAN_ROOT}" == "${share_default}" || "${ORCAN_ROOT}" == "${HOME}/.orcan" ]]; then
        rm -rf -- "${ORCAN_ROOT}"
        orcan_info "removed ${ORCAN_ROOT}"
    else
        orcan_warn "leaving ORCAN_ROOT in place (dev checkout?): ${ORCAN_ROOT}"
        orcan_warn "delete manually if desired"
    fi

    if (( purge )); then
        orcan_load_env 2>/dev/null || true
        local data="${ORCAN_DATA:-${XDG_CONFIG_HOME:-${HOME}/.config}/orcan}"
        printf 'WARNING: delete host data %s (Cursor/Claude login, caches)?\n' "${data}"
        printf "Type yes to purge: "
        read -r answer || true
        if [[ "${answer}" == "yes" ]]; then
            rm -rf -- "${data}"
            orcan_ok "removed ${data}"
        else
            orcan_info "kept ${data}"
        fi
    fi

    orcan_ok "uninstall finished"
}
