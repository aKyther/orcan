#!/usr/bin/env bash
# Container entrypoint: initialize Cursor home defaults, then exec CMD.

set -Eeuo pipefail

INIT_SCRIPT="${INIT_CURSOR_HOME_SCRIPT:-/usr/local/bin/init-cursor-home}"

run_init() {
    if [[ ! -x "${INIT_SCRIPT}" ]]; then
        printf 'Warning: init script not found or not executable: %s\n' "${INIT_SCRIPT}" >&2
        return 0
    fi

    # Runs as the non-root image user. Created files already belong to that user.
    "${INIT_SCRIPT}"
}

main() {
    run_init

    if [[ "$#" -eq 0 ]]; then
        set -- bash
    fi

    exec "$@"
}

main "$@"
