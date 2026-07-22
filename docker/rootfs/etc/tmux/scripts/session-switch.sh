#!/usr/bin/env bash
# Switch tmux session (one cind workspace = one session). ttyd-safe.
set -Eeuo pipefail

# Create any missing workspace sessions so the list is complete.
if command -v cursor-tmux-bootstrap-workspaces >/dev/null 2>&1; then
    cursor-tmux-bootstrap-workspaces 2>/dev/null || true
fi

# Native session picker — works in ttyd (unlike display-popup + fzf).
tmux choose-tree -Zs
