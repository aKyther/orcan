# orcan developer aliases — sourced from interactive shells.
# Safe for this container (isolated); skip-permission aliases are intentional.

# ------------------------------------------------------------------------------
# Listing / navigation
# ------------------------------------------------------------------------------

if command -v eza >/dev/null 2>&1; then
    alias ls='eza'
    alias ll='eza -lah --git'
    alias la='eza -la'
    alias lt='eza -lah --git --tree --level=2'
else
    alias ll='ls -lah'
    alias la='ls -la'
fi

alias ..='cd ..'
alias ...='cd ../..'
alias -- -='cd -'

# ------------------------------------------------------------------------------
# Search / view
# ------------------------------------------------------------------------------

alias grep='grep --color=auto'
alias g='rg'
alias ff='fd'
if command -v bat >/dev/null 2>&1; then
    alias cat='bat --paging=never'
fi

# ------------------------------------------------------------------------------
# Git / Docker (short)
# ------------------------------------------------------------------------------

alias gs='git status -sb'
alias gd='git diff'
alias ga='git add'
alias gaa='git add -A'
alias gc='git commit'
alias gcam='git commit -am'
alias gp='git push'
alias gpl='git pull'
alias gco='git checkout'
alias gb='git branch'
alias gl='git log --oneline --graph --decorate -20'
if command -v lazygit >/dev/null 2>&1; then
    alias lg='lazygit'
fi
alias dc='docker compose'
alias dps='docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'

# ------------------------------------------------------------------------------
# AI CLIs — normal vs "just go" (skip approval prompts)
# ------------------------------------------------------------------------------
# Container is the sandbox; these are for interactive ttyd/tmux use.

alias cc='claude'
# Skip permission prompts (Claude Code bypassPermissions).
alias ccy='claude --dangerously-skip-permissions'
alias claude-yolo='claude --dangerously-skip-permissions'

if command -v agent >/dev/null 2>&1; then
    alias ag='agent'
    # Cursor Agent: allow tools unless explicitly denied (--yolo == --force).
    alias agy='agent --yolo'
    alias agent-yolo='agent --yolo'
fi

# Opt-in tmux delivery shortcuts. --with-redis / --with-executor sets this
# flag; defining aliases must not probe Redis or start background services.
# exec replaces the pane shell, as required by the registered agent wrapper.
if [ "${ORCAN_REDIS_ENABLED:-0}" = "1" ] && command -v orcan-executor >/dev/null 2>&1; then
    alias codex-tmux='exec orcan-executor agent -- codex'
    alias codex-tmux-yolo='exec orcan-executor agent -- codex --dangerously-bypass-approvals-and-sandbox'
    alias codex-yolo-tmux='exec orcan-executor agent -- codex --dangerously-bypass-approvals-and-sandbox'
    alias claude-tmux='exec orcan-executor agent -- claude'
    alias cc-tmux='exec orcan-executor agent -- claude'
    alias claude-tmux-yolo='exec orcan-executor agent -- claude --dangerously-skip-permissions'
    alias claude-yolo-tmux='exec orcan-executor agent -- claude --dangerously-skip-permissions'
    alias ccy-tmux='exec orcan-executor agent -- claude --dangerously-skip-permissions'
    if command -v agent >/dev/null 2>&1; then
        alias agent-tmux='exec orcan-executor agent -- agent'
        alias ag-tmux='exec orcan-executor agent -- agent'
        alias agent-tmux-yolo='exec orcan-executor agent -- agent --yolo'
        alias agent-yolo-tmux='exec orcan-executor agent -- agent --yolo'
        alias agy-tmux='exec orcan-executor agent -- agent --yolo'
    fi
fi

# Context handoff (workspace root)
alias brief='orcan-session-brief'
alias ctx='orcan-context-status'

# ------------------------------------------------------------------------------
# Python
# ------------------------------------------------------------------------------

alias py='python3'
alias uvr='uv run'
