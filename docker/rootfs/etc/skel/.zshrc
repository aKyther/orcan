# cind interactive zsh — snippets in ~/.zshrc.d/

# History (file path set via HISTFILE env from Compose)
HISTSIZE=50000
SAVEHIST=50000
setopt SHARE_HISTORY
setopt HIST_IGNORE_DUPS
setopt HIST_IGNORE_SPACE
setopt EXTENDED_HISTORY
setopt INTERACTIVE_COMMENTS
setopt AUTO_CD
setopt AUTO_PUSHD
setopt PUSHD_IGNORE_DUPS

mkdir -p "${HOME}/.cache/zsh"

# Completion
autoload -Uz compinit
compinit -d "${HOME}/.cache/zsh/zcompdump" 2>/dev/null || compinit

# Snippets (PATH, workspace cwd, aliases, plugins, starship)
for f in "${HOME}"/.zshrc.d/*.zsh(N); do
  [[ -r "${f}" ]] && source "${f}"
done
