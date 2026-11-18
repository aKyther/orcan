#!/usr/bin/env bash
# shellcheck shell=bash
orcan_cmd_storage() {
    case "${1:-report}" in
        help|-h|--help)
            printf '%s\n' 'orcan storage [report | clean [--apply] [--archived-reports] | studio [--apply] | docker]' \
                'Report executor-owned data and shared cache sizes in the running instance.' \
                'clean previews expired clean jobs and unused snapshots; --apply executes.' \
                'Modified worktrees, shared caches and Docker data are preserved; completed logs expire independently.' \
                'docker reports daemon and builder storage without deleting anything.'
            ;;
        studio)
            shift
            orcan_host_python "${ORCAN_SCRIPTS}/studio-build-storage.py" --root "${ORCAN_ROOT}" "$@"
            ;;
        docker)
            shift
            orcan_host_python "${ORCAN_SCRIPTS}/build-storage.py" --root "${ORCAN_ROOT}" "$@"
            ;;
        *)
            # shellcheck source=executor.sh
            source "${ORCAN_CLI_DIR}/commands/executor.sh"
            orcan_cmd_executor storage "$@"
            ;;
    esac
}
