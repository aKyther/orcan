# Cursor CLI Dev Container shell setup
# Sourced from ~/.bashrc for interactive shells.

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$HOME/.local/share/pnpm:$HOME/go/bin:/usr/local/go/bin:/usr/local/cargo/bin:${PATH:-}"

alias ls='eza'
alias ll='eza -lah --git'
alias la='eza -la'
alias cat='bat --paging=never'
alias dc='docker compose'

# Path parity: enter the same absolute project path as on the host.
if [[ -n "${PROJECT_DIR:-}" && -d "${PROJECT_DIR}" ]]; then
    cd "${PROJECT_DIR}" || printf 'Warning: could not cd to PROJECT_DIR=%s\n' "${PROJECT_DIR}" >&2
fi

# tmux is started by cursor-ttyd (browser terminal), not here.
