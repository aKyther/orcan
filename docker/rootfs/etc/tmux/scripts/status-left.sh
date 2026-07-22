#!/usr/bin/env bash
# Left status: prefix · workspace · session (colourful, readable in ttyd).
set -Eeuo pipefail

prefix='#[fg=colour240]○ '
if [[ "$(tmux display -p '#{client_prefix}' 2>/dev/null || echo 0)" == "1" ]]; then
    prefix='#[fg=colour208,bold]◉ '
fi

workspace="$(tmux show-environment -g CIND_WORKSPACE_NAME 2>/dev/null | cut -d= -f2- || true)"
session="$(tmux display -p '#{session_name}' 2>/dev/null || echo session)"

if [[ -n "${workspace}" ]]; then
    if [[ "${workspace}" == "${session}" ]]; then
        printf '%s#[fg=colour81,bold] %s  ' "${prefix}" "${workspace}"
    else
        printf '%s#[fg=colour81,bold] %s #[fg=colour240]│ #[fg=colour117,bold]%s  ' \
            "${prefix}" "${workspace}" "${session}"
    fi
else
    project="$(tmux show-environment -g CIND_PROJECT_NAME 2>/dev/null | cut -d= -f2- || true)"
    if [[ -n "${project}" && "${project}" != "${session}" ]]; then
        printf '%s#[fg=colour81,bold] %s #[fg=colour240]│ #[fg=colour117,bold]%s  ' \
            "${prefix}" "${project}" "${session}"
    else
        printf '%s#[fg=colour117,bold]%s  ' "${prefix}" "${session}"
    fi
fi
