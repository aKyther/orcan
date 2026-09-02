# Curated zsh plugins (Debian packages + fzf). No download at runtime.
# Colours aligned with orcan graphite / muted plum (ttyd + desktop).

# Autosuggestions — quiet ghost text
if [[ -r /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh ]]; then
    ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE='fg=#554e61'
    ZSH_AUTOSUGGEST_STRATEGY=(history completion)
    source /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh
fi

# fzf key bindings + completion (Ctrl-R / Ctrl-T / Alt-C)
if command -v fzf >/dev/null 2>&1; then
    # Borderless compact layout; keep ASCII-safe (no Nerd Font required).
    export FZF_DEFAULT_OPTS="${FZF_DEFAULT_OPTS:-} \
--color=bg:#0e0c13,bg+:#211b29,fg:#b9b3c2,fg+:#d8d2e2 \
--color=hl:#9b87b8,hl+:#b9a7d6,info:#756f82,marker:#9b87b8 \
--color=prompt:#9b87b8,spinner:#aa9bc2,pointer:#b9a7d6,border:#4a3d59 \
--height=40% --layout=reverse --border=none --info=inline"
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
    # Muted violet commands / clear red errors (if styles are available).
    typeset -A ZSH_HIGHLIGHT_STYLES
    ZSH_HIGHLIGHT_STYLES[command]='fg=#aa9bc2'
    ZSH_HIGHLIGHT_STYLES[builtin]='fg=#9b87b8'
    ZSH_HIGHLIGHT_STYLES[alias]='fg=#9b87b8'
    ZSH_HIGHLIGHT_STYLES[path]='fg=#918a9d'
    ZSH_HIGHLIGHT_STYLES[unknown-token]='fg=#d98282'
fi
