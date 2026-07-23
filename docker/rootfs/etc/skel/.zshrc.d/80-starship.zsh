# Starship prompt (autodetects git / language / cwd). Skip if missing.
if command -v starship >/dev/null 2>&1; then
    eval "$(starship init zsh)"
fi
