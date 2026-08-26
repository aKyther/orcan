#!/usr/bin/env bash
# Short live label for a pane — used by pane-border-format and
# automatic-rename-format so the title follows the process (claude, review, …)
# instead of a one-shot `select-pane -T` pin.
#
# Usage: pane-label.sh [pane_id]
# Tests:  PANE_LABEL_CMD=bash PANE_LABEL_CMDLINE='…orcan-context-review…' pane-label.sh
set -Eeuo pipefail

pane="${1:-}"

# Host tests set PANE_LABEL_CMD (even to "") to skip tmux /proc.
if [[ -n "${PANE_LABEL_CMD+x}" ]]; then
    cmd="${PANE_LABEL_CMD}"
    cmdline="${PANE_LABEL_CMDLINE-}"
else
    cmd=""
    cmdline=""
    if [[ -z "${pane}" ]]; then
        pane="$(tmux display -p '#{pane_id}' 2>/dev/null || true)"
    fi
    if [[ -z "${pane}" ]]; then
        printf '%s' '?'
        exit 0
    fi
    cmd="$(tmux display -p -t "${pane}" '#{pane_current_command}' 2>/dev/null || true)"
    pid="$(tmux display -p -t "${pane}" '#{pane_pid}' 2>/dev/null || true)"
    if [[ -n "${pid}" && -r "/proc/${pid}/cmdline" ]]; then
        cmdline="$(tr '\0' ' ' <"/proc/${pid}/cmdline" 2>/dev/null || true)"
    fi
fi

cmd="${cmd:-}"
cmdline="${cmdline:-}"
# Lowercase for matching (bash 4+). Keep original cmd for the fallback label.
haystack="$(printf '%s' "${cmd} ${cmdline}" | tr '[:upper:]' '[:lower:]')"

if [[ "${haystack}" == *orcan-context-review* ]]; then
    printf '%s' 'review'
    exit 0
fi

# Known agent / coding CLIs — first match wins (substring on cmdline).
for name in claude codex aider gemini amp opencode cursor-agent; do
    if [[ "${haystack}" == *"${name}"* ]]; then
        printf '%s' "${name}"
        exit 0
    fi
done

# Bare `agent` command (not agent-launcher / …-agent as a path segment only).
base="${cmd##*/}"
base_lc="$(printf '%s' "${base}" | tr '[:upper:]' '[:lower:]')"
if [[ "${base_lc}" == "agent" ]]; then
    printf '%s' 'agent'
    exit 0
fi

printf '%s' "${base:-zsh}"
