# Cursor CLI Dev Container shell setup
# Sourced from ~/.bashrc for interactive shells.

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$HOME/.local/share/pnpm:$HOME/go/bin:/usr/local/go/bin:/usr/local/cargo/bin:${PATH:-}"

alias ls='eza'
alias ll='eza -lah --git'
alias la='eza -la'
alias cat='bat --paging=never'
alias dc='docker compose'

# Start TMUX only for interactive TTY sessions.
if command -v tmux >/dev/null 2>&1 \
    && [[ -z "${TMUX:-}" ]] \
    && [[ -t 0 ]]; then
    exec tmux new-session -A -s cursor
fi
