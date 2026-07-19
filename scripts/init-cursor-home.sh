#!/usr/bin/env bash
# Copy missing Cursor defaults from /opt/cursor-defaults into ${HOME}/.cursor.
# Idempotent: never overwrites existing files.

set -Eeuo pipefail

DEFAULTS_DIR="${CURSOR_DEFAULTS_DIR:-/opt/cursor-defaults}"
CURSOR_HOME="${CURSOR_HOME:-${HOME:?HOME is not set}/.cursor}"

CREATED=0
SKIPPED=0
MISSING=0

log() {
    printf '%s\n' "$*"
}

ensure_dirs() {
    mkdir -p "${CURSOR_HOME}"
}

copy_missing_files() {
    local source_file relative_path target_file

    if [[ ! -d "${DEFAULTS_DIR}" ]]; then
        log "Missing: defaults directory ${DEFAULTS_DIR}"
        MISSING=1
        return 0
    fi

    while IFS= read -r -d '' source_file; do
        relative_path="${source_file#"${DEFAULTS_DIR}"/}"
        target_file="${CURSOR_HOME}/${relative_path}"

        mkdir -p "$(dirname "${target_file}")"

        if [[ -e "${target_file}" ]]; then
            log "Skipped: ${target_file}"
            SKIPPED=$((SKIPPED + 1))
            continue
        fi

        cp -- "${source_file}" "${target_file}"
        chmod u+rw -- "${target_file}" 2>/dev/null || true
        log "Created: ${target_file}"
        CREATED=$((CREATED + 1))
    done < <(find "${DEFAULTS_DIR}" -type f -print0 | sort -z)
}

print_summary() {
    log ""
    log "Cursor home init summary"
    log "  source : ${DEFAULTS_DIR}"
    log "  target : ${CURSOR_HOME}"
    log "  created: ${CREATED}"
    log "  skipped: ${SKIPPED}"
    if (( MISSING > 0 )); then
        log "  status : defaults missing (noop)"
    else
        log "  status : ok"
    fi
}

main() {
    ensure_dirs
    copy_missing_files
    print_summary
}

main "$@"
