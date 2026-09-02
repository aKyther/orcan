#!/usr/bin/env bash
# Short live label for a pane — used by pane-border-format so the title
# follows the process (claude, review, …) instead of a one-shot
# `select-pane -T` pin.
#
# Usage: pane-label.sh [pane_current_command] [pane_pid]
#
# Both args come straight from native tmux format variables, so this never
# shells back into `tmux display`. That mattered: the old pane-id form ran
# three `tmux` round-trips per border redraw, and in a busy agent pane
# (codex / cursor-agent constantly spawning children) tmux spent its single
# thread forking this script instead of draining keystrokes — visible input
# lag. Now the hot path spawns nothing but this shell.
set -Eeuo pipefail

# Host tests set PANE_LABEL_CMD (even to "") to bypass the argv / /proc path.
if [[ -n "${PANE_LABEL_CMD+x}" ]]; then
    cmd="${PANE_LABEL_CMD}"
    cmdline="${PANE_LABEL_CMDLINE-}"
else
    cmd="${1:-}"
    pid="${2:-}"
    cmdline=""
    if [[ -n "${pid}" && -r "/proc/${pid}/cmdline" ]]; then
        cmdline="$(tr '\0' ' ' <"/proc/${pid}/cmdline" 2>/dev/null || true)"
    fi
fi

cmd="${cmd:-}"
cmdline="${cmdline:-}"
# Lowercase for matching (bash 4+); no subshell.
haystack="${cmd} ${cmdline}"
haystack="${haystack,,}"

# Known agent / coding CLIs — first match wins (substring on cmd + cmdline).
for name in claude codex aider gemini amp opencode cursor-agent; do
    if [[ "${haystack}" == *"${name}"* ]]; then
        printf '%s' "${name}"
        exit 0
    fi
done

# Bare `agent` command (not agent-launcher / …-agent as a path segment only).
base="${cmd##*/}"
if [[ "${base,,}" == "agent" ]]; then
    printf '%s' 'agent'
    exit 0
fi

printf '%s' "${base:-zsh}"
