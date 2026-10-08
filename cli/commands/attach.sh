#!/usr/bin/env bash
# shellcheck shell=bash
# Attach a native terminal to one configured workspace tmux session.

# Reuse Docker exec and workspace-history helpers from the local entry command.
# shellcheck source=enter.sh
source "${ORCAN_CLI_DIR}/commands/enter.sh"

orcan_cmd_attach() {
    local workspace="" rows name root session _repos

    case "${1:-}" in
        -h|--help)
            cat <<'EOF'
usage: orcan attach WORKSPACE

Create or resume the tmux session for one configured workspace and attach this
terminal to it. WORKSPACE is the configured workspace name, not the tmux name.

Examples:
  orcan attach orcan-dev
  ssh -tt my-enclave 'orcan attach orcan-dev'
EOF
            return 0
            ;;
    esac

    [[ $# -eq 1 ]] || orcan_usage_error "usage: orcan attach WORKSPACE"
    workspace="$1"
    [[ -n "${workspace}" ]] || orcan_usage_error "workspace name must not be empty"

    orcan_require_docker
    rows="$(orcan_enter_exec orcan-workspaces list)" \
        || orcan_die "could not read workspaces from the running container"

    name=""
    root=""
    session=""
    while IFS=$'\t' read -r name root session _repos; do
        [[ "${name}" == "${workspace}" ]] || continue
        [[ -n "${root}" && -n "${session}" ]] || break
        orcan_record_workspace_use || true
        orcan_info "attaching workspace: ${workspace}"
        orcan_enter_exec cursor-tmux-workspace-attach "${session}" "${root}" "${name}"
        return $?
    done <<< "${rows}"

    orcan_die "workspace not found: ${workspace} (run: orcan context show)"
}
