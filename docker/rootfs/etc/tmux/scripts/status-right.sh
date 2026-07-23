#!/usr/bin/env bash
# Right status (thin): optional AI · brief · time.
# Heavy/global metrics and cwd live elsewhere (pane border / host tools) — keep ttyd readable.
set -Eeuo pipefail

parts=()

ai_usage=""
if [[ -x /etc/tmux/scripts/ai-usage.sh ]]; then
    ai_usage="$(timeout 0.3 /etc/tmux/scripts/ai-usage.sh 2>/dev/null || true)"
elif [[ -f /etc/tmux/scripts/ai-usage.sh ]]; then
    ai_usage="$(timeout 0.3 python3 /etc/tmux/scripts/ai-usage.sh 2>/dev/null || true)"
fi
if [[ -n "${ai_usage}" ]]; then
    parts+=("${ai_usage}")
fi

brief_root="$(tmux show-environment CIND_WORKSPACE_ROOT 2>/dev/null | cut -d= -f2- || true)"
if [[ -z "${brief_root}" ]]; then
    brief_root="${CIND_WORKSPACE_ROOT:-}"
fi
if [[ -z "${brief_root}" ]]; then
    pane_path="$(tmux display -p '#{pane_current_path}' 2>/dev/null || true)"
    case "${pane_path}" in
        /home/developer/workspaces/*)
            brief_root="$(printf '%s' "${pane_path}" | cut -d/ -f1-5)"
            ;;
    esac
fi
if [[ -n "${brief_root}" && -f "${brief_root}/.cind/session-brief.md" ]]; then
    parts+=("#[fg=colour114,bold]brief")
fi

parts+=("#[fg=colour228,bold]$(date +%H:%M)")

out=" "
sep='#[fg=colour240] · #[default]'
first=1
for segment in "${parts[@]}"; do
    if (( first )); then
        out+="${segment}"
        first=0
    else
        out+="${sep}${segment}"
    fi
done
out+=' '

printf '%s' "${out}"
