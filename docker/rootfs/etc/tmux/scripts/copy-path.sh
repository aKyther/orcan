#!/usr/bin/env bash
# Copy current pane path into tmux buffer.
set -Eeuo pipefail

path="$(tmux display -p '#{pane_current_path}')"
tmux set-buffer -b orcan-path "${path}"
tmux display-message " path copied: ${path} (paste with prefix ] ) "
