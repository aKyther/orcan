#!/usr/bin/env bash
# Right status: git · path · load · mem · battery · time (fast; colourful segments).
set -Eeuo pipefail

pane_path="$(tmux display -p '#{pane_current_path}' 2>/dev/null || pwd)"
home="${HOME:-/home/developer}"

branch=""
if command -v git >/dev/null 2>&1; then
    branch="$(timeout 0.2 git -C "${pane_path}" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
    if [[ "${branch}" == "HEAD" ]]; then
        branch="$(timeout 0.2 git -C "${pane_path}" rev-parse --short HEAD 2>/dev/null || true)"
    fi
fi

cwd="${pane_path}"
if [[ "${cwd}" == "${home}"* ]]; then
    cwd="~${cwd#"${home}"}"
fi
if ((${#cwd} > 32)); then
    cwd="…${cwd: -31}"
fi

load=""
if [[ -r /proc/loadavg ]]; then
    load="$(awk '{printf "%.1f", $1}' /proc/loadavg 2>/dev/null || true)"
fi

mem=""
if command -v free >/dev/null 2>&1; then
    mem="$(free -m 2>/dev/null | awk '/^Mem:/ { if ($2>0) printf "%.0f%%", ($3/$2)*100 }')"
fi

battery=""
for cap in /sys/class/power_supply/BAT*/capacity; do
    if [[ -r "${cap}" ]]; then
        battery="$(cat "${cap}" 2>/dev/null | tr -d '[:space:]')"
        break
    fi
done

time_str="$(date +%H:%M)"

parts=()

if [[ -n "${branch}" ]]; then
    parts+=("#[fg=colour141,bold]⎇ ${branch}")
fi
parts+=("#[fg=colour252]${cwd}")

if [[ -n "${load}" ]]; then
    parts+=("#[fg=colour109]cpu ${load}")
fi
if [[ -n "${mem}" ]]; then
    parts+=("#[fg=colour109]mem ${mem}")
fi

ai_usage=""
if [[ -x /etc/tmux/scripts/ai-usage.sh ]]; then
    ai_usage="$(timeout 0.3 /etc/tmux/scripts/ai-usage.sh 2>/dev/null || true)"
elif [[ -f /etc/tmux/scripts/ai-usage.sh ]]; then
    ai_usage="$(timeout 0.3 python3 /etc/tmux/scripts/ai-usage.sh 2>/dev/null || true)"
fi
if [[ -n "${ai_usage}" ]]; then
    parts+=("${ai_usage}")
fi

# Session handoff marker (tmux session env, else path under workspaces/).
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

if [[ -n "${battery}" && "${battery}" =~ ^[0-9]+$ ]]; then
    bat_colour='109'
    if (( battery < 20 )); then
        bat_colour='203'
    elif (( battery < 50 )); then
        bat_colour='208'
    fi
    parts+=("#[fg=colour${bat_colour}]🔋${battery}%")
fi
parts+=("#[fg=colour228,bold]${time_str}")

out="#[fg=colour235,bg=colour234] "
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
out+=' #[default]'

printf '%s' "${out}"
