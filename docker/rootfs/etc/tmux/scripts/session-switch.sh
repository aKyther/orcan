#!/usr/bin/env bash
# Fuzzy or prompted session switch (ttyd-safe).
set -Eeuo pipefail

if tmux display-popup -h >/dev/null 2>&1 && command -v fzf >/dev/null 2>&1; then
    tmux display-popup -E -w 50% -h 40% \
        "s=\$(tmux list-sessions -F '#{session_name}' | fzf --reverse --height=100% --prompt='session> '); [ -n \"\$s\" ] && tmux switch-client -t \"=\$s\""
    exit 0
fi

tmux command-prompt -I "#{session_name}" -p 'switch session:' 'switch-client -t "%%"'
