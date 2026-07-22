#!/usr/bin/env bash
# Right status segment: git, host, cwd, load, memory, battery, time.
# Keep fast — runs every status-interval (5s).
set -Eeuo pipefail

parts=()

# Git branch (pane cwd, 200ms cap)
pane_path="$(tmux display -p '#{pane_current_path}' 2>/dev/null || pwd)"
branch=""
if command -v git >/dev/null 2>&1; then
    branch="$(timeout 0.2 git -C "${pane_path}" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
    if [[ "${branch}" == "HEAD" ]]; then
        branch="$(timeout 0.2 git -C "${pane_path}" rev-parse --short HEAD 2>/dev/null || true)"
    fi
fi
if [[ -n "${branch}" ]]; then
    parts+=("⎇ ${branch}")
fi

# Hostname (short)
host="$(hostname -s 2>/dev/null || hostname)"
parts+=("${host}")

# Current directory (basename or ~)
cwd="${pane_path}"
home="${HOME:-/home/developer}"
if [[ "${cwd}" == "${home}"* ]]; then
    cwd="~${cwd#"${home}"}"
fi
if ((${#cwd} > 28)); then
    cwd="…${cwd: -27}"
fi
parts+=("${cwd}")

# CPU load (1m average — lightweight proxy)
if [[ -r /proc/loadavg ]]; then
    load="$(awk '{printf "%.1f", $1}' /proc/loadavg 2>/dev/null || true)"
    [[ -n "${load}" ]] && parts+=("cpu ${load}")
fi

# Memory usage percent
if command -v free >/dev/null 2>&1; then
    mem="$(free -m 2>/dev/null | awk '/^Mem:/ { if ($2>0) printf "%.0f%%", ($3/$2)*100 }')"
    [[ -n "${mem}" ]] && parts+=("mem ${mem}")
fi

# Battery (Linux / WSL when exposed)
battery=""
for cap in /sys/class/power_supply/BAT*/capacity; do
    if [[ -r "${cap}" ]]; then
        battery="$(cat "${cap}" 2>/dev/null | tr -d '[:space:]')"
        break
    fi
done
if [[ -n "${battery}" && "${battery}" =~ ^[0-9]+$ ]]; then
    parts+=("🔋${battery}%")
fi

# Time
parts+=("$(date +%H:%M)")

printf '%s' "$(IFS=' · '; echo "${parts[*]}")"
