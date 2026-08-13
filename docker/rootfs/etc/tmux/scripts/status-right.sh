#!/usr/bin/env bash
# Right status: AI · brief · git · battery (clock + cpu/mem moved to pane-border-format, top-right)
# Icon prefixes (Unicode) — works with Menlo/Monaco in ttyd; no Nerd Font required.
set -Eeuo pipefail

pane_path="$(tmux display -p '#{pane_current_path}' 2>/dev/null || pwd)"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

parts=()

ai_usage=""
if [[ -x "${script_dir}/ai-usage.sh" ]]; then
    ai_usage="$(timeout 0.3 "${script_dir}/ai-usage.sh" 2>/dev/null || true)"
elif [[ -x /etc/tmux/scripts/ai-usage.sh ]]; then
    ai_usage="$(timeout 0.3 /etc/tmux/scripts/ai-usage.sh 2>/dev/null || true)"
elif [[ -f /etc/tmux/scripts/ai-usage.sh ]]; then
    ai_usage="$(timeout 0.3 python3 /etc/tmux/scripts/ai-usage.sh 2>/dev/null || true)"
fi
if [[ -n "${ai_usage}" ]]; then
    parts+=("${ai_usage}")
fi

brief_root="$(tmux show-environment ORCAN_WORKSPACE_ROOT 2>/dev/null | cut -d= -f2- || true)"
if [[ -z "${brief_root}" ]]; then
    brief_root="${ORCAN_WORKSPACE_ROOT:-}"
fi
if [[ -z "${brief_root}" ]]; then
    case "${pane_path}" in
        /home/developer/workspaces/*)
            brief_root="$(printf '%s' "${pane_path}" | cut -d/ -f1-5)"
            ;;
    esac
fi
if [[ -n "${brief_root}" && -f "${brief_root}/.orcan/session-brief.md" ]]; then
    parts+=("#[fg=#4ade80,bold]◆")
fi

branch=""
if command -v git >/dev/null 2>&1; then
    branch="$(timeout 0.2 git -C "${pane_path}" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
    if [[ "${branch}" == "HEAD" ]]; then
        branch="$(timeout 0.2 git -C "${pane_path}" rev-parse --short HEAD 2>/dev/null || true)"
    fi
fi
if [[ -n "${branch}" ]]; then
    parts+=("#[fg=#7dd3fc,bold]⎇ ${branch}")
fi

battery=""
for cap in /sys/class/power_supply/BAT*/capacity; do
    if [[ -r "${cap}" ]]; then
        battery="$(cat "${cap}" 2>/dev/null | tr -d '[:space:]')"
        break
    fi
done
if [[ -n "${battery}" && "${battery}" =~ ^[0-9]+$ ]]; then
    bat_colour='#67e8f9'
    if (( battery < 20 )); then
        bat_colour='#f87171'
    elif (( battery < 50 )); then
        bat_colour='#fbbf24'
    fi
    parts+=("#[fg=${bat_colour}]⚡ ${battery}%")
fi

# Clock lives top-right in the pane border (status.conf pane-border-format).

out=" "
sep='#[fg=#334155] · #[default]'
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
