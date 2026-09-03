# Per-workspace shell history (host: $ORCAN_DATA/history/workspaces/<name>/).
# Sourced from devtools-env.sh and cursor-tmux-workspace-attach.
#
# Inside tmux each workspace session gets its own HISTFILE so ↑-history does
# not leak across workspaces. Outside tmux (or without ORCAN_WORKSPACE_NAME /
# WORKSPACE_NAME) callers keep the global fallback from devtools-env.sh.

orcan_sanitize_workspace_name() {
    local name="$1"
    name="$(printf '%s' "${name}" | tr -c 'A-Za-z0-9._-' '_')"
    name="${name##_}"
    name="${name%%_}"
    [[ -n "${name}" ]] || name="workspace"
    printf '%s\n' "${name:0:50}"
}

orcan_workspace_history_dir() {
    local ws_name="$1"
    local safe
    safe="$(orcan_sanitize_workspace_name "${ws_name}")"
    printf '%s\n' "${HOME}/.local/share/orcan/history/workspaces/${safe}"
}

orcan_workspace_histfile_path() {
    local ws_name="$1"
    local shell_kind="${2:-auto}"
    local dir base
    dir="$(orcan_workspace_history_dir "${ws_name}")"
    if [[ "${shell_kind}" == "auto" ]]; then
        if [[ -n "${ZSH_VERSION:-}" ]]; then
            shell_kind="zsh"
        elif [[ -n "${BASH_VERSION:-}" ]]; then
            shell_kind="bash"
        else
            shell_kind="zsh"
        fi
    fi
    case "${shell_kind}" in
        bash) base=".bash_history" ;;
        zsh | *) base=".zsh_history" ;;
    esac
    printf '%s\n' "${dir}/${base}"
}

orcan_resolve_workspace_name() {
    if [[ -n "${ORCAN_WORKSPACE_NAME:-}" ]]; then
        printf '%s\n' "${ORCAN_WORKSPACE_NAME}"
        return 0
    fi
    if [[ -n "${WORKSPACE_NAME:-}" ]]; then
        printf '%s\n' "${WORKSPACE_NAME}"
        return 0
    fi
    return 1
}

# Set HISTFILE to the current workspace file. Returns 1 when no workspace name
# is available (caller should keep the global default).
orcan_apply_workspace_histfile() {
    local ws_name histfile hist_dir
    ws_name="$(orcan_resolve_workspace_name)" || return 1
    histfile="$(orcan_workspace_histfile_path "${ws_name}")"
    hist_dir="$(dirname "${histfile}")"
    export HISTFILE="${histfile}"
    mkdir -p "${hist_dir}" 2>/dev/null || return 1
    return 0
}
