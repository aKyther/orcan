#!/usr/bin/env bash
# Left status segment: prefix indicator, project, session.
set -Eeuo pipefail

prefix='○ '
if [[ "$(tmux display -p '#{client_prefix}' 2>/dev/null || echo 0)" == "1" ]]; then
    prefix='◉ '
fi

project="$(tmux show-environment -g CIND_PROJECT_NAME 2>/dev/null | cut -d= -f2- || true)"
session="$(tmux display -p '#{session_name}' 2>/dev/null || echo session)"

if [[ -n "${project}" && "${project}" != "${session}" ]]; then
    printf '#[fg=colour208,bold]%s#[fg=colour81]%s#[fg=colour245] · %s' "${prefix}" "${project}" "${session}"
else
    printf '#[fg=colour208,bold]%s#[fg=colour81]%s' "${prefix}" "${session}"
fi
