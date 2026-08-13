# orcan interactive zsh — snippets in ~/.zshrc.d/

# History (file path set via HISTFILE env from Compose)
HISTSIZE=50000
SAVEHIST=50000
setopt SHARE_HISTORY
setopt HIST_IGNORE_DUPS
setopt HIST_IGNORE_ALL_DUPS
setopt HIST_IGNORE_SPACE
setopt HIST_REDUCE_BLANKS
setopt HIST_VERIFY
setopt EXTENDED_HISTORY
setopt INTERACTIVE_COMMENTS
setopt AUTO_CD
setopt AUTO_PUSHD
setopt PUSHD_IGNORE_DUPS
setopt PUSHD_SILENT

mkdir -p "${HOME}/.cache/zsh"

# Completion — menu select, case-insensitive, path-friendly
autoload -Uz compinit
compinit -d "${HOME}/.cache/zsh/zcompdump" 2>/dev/null || compinit
zstyle ':completion:*' menu select
zstyle ':completion:*' matcher-list 'm:{a-z}={A-Z}' 'r:|=*' 'l:|=* r:|=*'
zstyle ':completion:*' list-colors "${(s.:.)LS_COLORS}"
zstyle ':completion:*' group-name ''
zstyle ':completion:*:descriptions' format '%F{cyan}-- %d --%f'
setopt COMPLETE_IN_WORD
setopt ALWAYS_TO_END

# Snippets (PATH, workspace cwd, aliases, plugins, starship)
for f in "${HOME}"/.zshrc.d/*.zsh(N); do
  [[ -r "${f}" ]] && source "${f}"
done
