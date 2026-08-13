# Curated zsh plugins (Debian packages + fzf). No download at runtime.
# Colours aligned with orcan navy / subtle cyan (ttyd + desktop).

# Autosuggestions — faint cyan ghost text
if [[ -r /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh ]]; then
    ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE='fg=#475569'
    ZSH_AUTOSUGGEST_STRATEGY=(history completion)
    source /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh
fi

# fzf key bindings + completion (Ctrl-R / Ctrl-T / Alt-C)
if command -v fzf >/dev/null 2>&1; then
    # Navy/cyan layout; keep ASCII-safe (no Nerd Font glyphs required).
    export FZF_DEFAULT_OPTS="${FZF_DEFAULT_OPTS:-} \
--color=bg:#0a0e17,bg+:#152033,fg:#c8d3e0,fg+:#e2e8f0 \
--color=hl:#5eead4,hl+:#67e8f9,info:#64748b,marker:#5eead4 \
--color=prompt:#5eead4,spinner:#67e8f9,pointer:#67e8f9,border:#1e293b \
--height=40% --layout=reverse --border --info=inline"
    export FZF_CTRL_T_OPTS="--preview 'bat --color=always --style=plain --line-range=:80 {} 2>/dev/null || head -80 {}'"
    export FZF_ALT_C_OPTS="--preview 'eza -lah --color=always {} 2>/dev/null || ls -lah {}'"

    if [[ -r /usr/share/doc/fzf/examples/key-bindings.zsh ]]; then
        source /usr/share/doc/fzf/examples/key-bindings.zsh
    fi
    if [[ -r /usr/share/doc/fzf/examples/completion.zsh ]]; then
        source /usr/share/doc/fzf/examples/completion.zsh
    fi
fi

# Syntax highlighting must be last among plugins that wrap the ZLE
if [[ -r /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ]]; then
    source /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
    # Soft cyan commands / clear red errors (if styles are available).
    typeset -A ZSH_HIGHLIGHT_STYLES
    ZSH_HIGHLIGHT_STYLES[command]='fg=#67e8f9'
    ZSH_HIGHLIGHT_STYLES[builtin]='fg=#5eead4'
    ZSH_HIGHLIGHT_STYLES[alias]='fg=#5eead4'
    ZSH_HIGHLIGHT_STYLES[path]='fg=#94a3b8'
    ZSH_HIGHLIGHT_STYLES[unknown-token]='fg=#f87171'
fi
