# User dotfiles for the Orcan container (persisted on the host).
#
# Host path:   $ORCAN_DATA/dotfiles   (default: ~/.config/orcan/dotfiles)
# In container: ~/.config/orcan/dotfiles
#
# Image defaults (aliases, tmux under /etc/tmux, skel vim/zsh) stay as-is.
# Create any of the files below to extend or override — missing files are ignored.
#
#   aliases.sh           # sourced after image aliases (zsh + bash)
#   zshrc.d/*.zsh        # extra zsh snippets (after aliases)
#   bashrc.d/*.sh        # extra bash snippets
#   tmux.conf.local      # sourced after /etc/tmux/tmux.conf
#   vimrc.local          # sourced after default .vimrc
#   starship.toml        # if present, used as ~/.config/starship.toml
#   gitconfig.local      # included from ~/.gitconfig when present
#
# Examples live next to this README (*.example). Copy and drop the .example suffix.
#
# After editing: new shells pick up shell/vim changes; for tmux run
#   tmux source-file ~/.tmux.conf
# or detach/reattach. Recreate is NOT required (bind mount).
