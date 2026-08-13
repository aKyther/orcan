#!/usr/bin/env bash
# Left status: prefix indicator only. Workspace/session identity used to be
# repeated here as a pill, but it already shows at the top of the screen
# (pane-border-format's #{b:pane_current_path} — panes start in the
# workspace root) so it was pure duplication; dropped.
set -Eeuo pipefail

if [[ "$(tmux display -p '#{client_prefix}' 2>/dev/null || echo 0)" == "1" ]]; then
    printf '#[fg=#fbbf24,bold]◉ '
else
    printf '#[fg=#475569]○ '
fi
