# cind interactive shell setup (PATH + default cwd).
# Sourced from ~/.bashrc via ~/.bashrc.d/.

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$HOME/.local/share/pnpm:$HOME/go/bin:/usr/local/go/bin:/usr/local/cargo/bin:${PATH:-}"

# Aliases: /etc/cind/shell/aliases.sh (via 60-cind-aliases.sh).

# Inside tmux: only the *session* workspace root (never compose WORKSPACE_ROOT /
# CONTAINER_PROJECT_DIR — those always point at the first workspaces[] entry).
if [[ -n "${TMUX:-}" ]]; then
    if [[ -n "${CIND_WORKSPACE_ROOT:-}" && -d "${CIND_WORKSPACE_ROOT}" ]]; then
        cd "${CIND_WORKSPACE_ROOT}" || printf 'Warning: could not cd to CIND_WORKSPACE_ROOT=%s\n' "${CIND_WORKSPACE_ROOT}" >&2
    fi
elif [[ -n "${WORKSPACE_ROOT:-}" && -d "${WORKSPACE_ROOT}" ]]; then
    cd "${WORKSPACE_ROOT}" || printf 'Warning: could not cd to WORKSPACE_ROOT=%s\n' "${WORKSPACE_ROOT}" >&2
elif [[ -n "${CONTAINER_PROJECT_DIR:-}" && -d "${CONTAINER_PROJECT_DIR}" ]]; then
    cd "${CONTAINER_PROJECT_DIR}" || printf 'Warning: could not cd to CONTAINER_PROJECT_DIR=%s\n' "${CONTAINER_PROJECT_DIR}" >&2
elif [[ -n "${PROJECT_DIR:-}" && -d "${PROJECT_DIR}" ]]; then
    cd "${PROJECT_DIR}" || printf 'Warning: could not cd to PROJECT_DIR=%s\n' "${PROJECT_DIR}" >&2
fi

# tmux is started by cursor-ttyd (browser terminal), not here.
