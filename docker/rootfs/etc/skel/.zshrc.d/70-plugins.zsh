# Curated zsh plugins (Debian packages + fzf). No download at runtime.

# Autosuggestions
if [[ -r /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh ]]; then
    source /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh
fi

# fzf key bindings + completion (Ctrl-R / Ctrl-T / Alt-C)
if command -v fzf >/dev/null 2>&1; then
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
fi
