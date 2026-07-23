#!/usr/bin/env bash
# Right status: AI · brief · git · cpu · mem · battery · time
# (Global metrics live here; cwd/command stay on pane-border footers.)
set -Eeuo pipefail

pane_path="$(tmux display -p '#{pane_current_path}' 2>/dev/null || pwd)"
home="${HOME:-/home/developer}"

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
    case "${pane_path}" in
        /home/developer/workspaces/*)
            brief_root="$(printf '%s' "${pane_path}" | cut -d/ -f1-5)"
            ;;
    esac
fi
if [[ -n "${brief_root}" && -f "${brief_root}/.cind/session-brief.md" ]]; then
    parts+=("#[fg=colour114,bold]brief")
fi

branch=""
if command -v git >/dev/null 2>&1; then
    branch="$(timeout 0.2 git -C "${pane_path}" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
    if [[ "${branch}" == "HEAD" ]]; then
        branch="$(timeout 0.2 git -C "${pane_path}" rev-parse --short HEAD 2>/dev/null || true)"
    fi
fi
if [[ -n "${branch}" ]]; then
    # Plain "git" label — avoids Nerd Font / special glyphs in ttyd
    parts+=("#[fg=colour141,bold]git ${branch}")
fi

load=""
if [[ -r /proc/loadavg ]]; then
    load="$(awk '{printf "%.1f", $1}' /proc/loadavg 2>/dev/null || true)"
fi
if [[ -n "${load}" ]]; then
    parts+=("#[fg=colour109]cpu ${load}")
fi

mem=""
if command -v free >/dev/null 2>&1; then
    mem="$(free -m 2>/dev/null | awk '/^Mem:/ { if ($2>0) printf "%.0f%%", ($3/$2)*100 }')"
fi
if [[ -n "${mem}" ]]; then
    parts+=("#[fg=colour109]mem ${mem}")
fi

battery=""
for cap in /sys/class/power_supply/BAT*/capacity; do
    if [[ -r "${cap}" ]]; then
        battery="$(cat "${cap}" 2>/dev/null | tr -d '[:space:]')"
        break
    fi
done
if [[ -n "${battery}" && "${battery}" =~ ^[0-9]+$ ]]; then
    bat_colour='109'
    if (( battery < 20 )); then
        bat_colour='203'
    elif (( battery < 50 )); then
        bat_colour='208'
    fi
    parts+=("#[fg=colour${bat_colour}]bat ${battery}%")
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
