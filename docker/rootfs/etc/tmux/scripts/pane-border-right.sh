#!/usr/bin/env bash
# Right side of the pane-border-status top strip: cpu · mem.
# Icons/colours match status-right.sh (moved here from the bottom bar).
set -Eeuo pipefail

parts=()

load=""
if [[ -r /proc/loadavg ]]; then
    load="$(awk '{printf "%.1f", $1}' /proc/loadavg 2>/dev/null || true)"
fi
if [[ -n "${load}" ]]; then
    parts+=("#[fg=#67e8f9]⚙ ${load}")
fi

mem=""
if command -v free >/dev/null 2>&1; then
    mem="$(free -m 2>/dev/null | awk '/^Mem:/ { if ($2>0) printf "%.0f%%", ($3/$2)*100 }')"
fi
if [[ -n "${mem}" ]]; then
    parts+=("#[fg=#67e8f9]🧠 ${mem}")
fi

out=""
sep='#[fg=#334155] │ #[default]'
first=1
for segment in "${parts[@]}"; do
    if (( first )); then
        out+="${segment}"
        first=0
    else
        out+="${sep}${segment}"
    fi
done

printf '%s' "${out}"
