#!/usr/bin/env bash
# Left status: prefix · workspace pill (navy / subtle cyan).
set -Eeuo pipefail

prefix='#[fg=#475569]○ '
if [[ "$(tmux display -p '#{client_prefix}' 2>/dev/null || echo 0)" == "1" ]]; then
    prefix='#[fg=#fbbf24,bold]◉ '
fi

workspace="$(tmux show-environment ORCAN_WORKSPACE_NAME 2>/dev/null | cut -d= -f2- || true)"
if [[ -z "${workspace}" ]]; then
    workspace="$(tmux show-environment -g ORCAN_WORKSPACE_NAME 2>/dev/null | cut -d= -f2- || true)"
fi
session="$(tmux display -p '#{session_name}' 2>/dev/null || echo session)"

pill() {
    # $1 = label
    printf '%s#[fg=#0a0e17,bg=#5eead4,bold] %s #[default]' "${prefix}" "$1"
}

if [[ -n "${workspace}" ]]; then
    if [[ "${workspace}" == "${session}" ]]; then
        pill "${workspace}"
        printf ' '
    else
        printf '%s#[fg=#0a0e17,bg=#5eead4,bold] %s #[fg=#67e8f9,bg=#164e63,bold] %s #[default] ' \
            "${prefix}" "${workspace}" "${session}"
    fi
else
    project="$(tmux show-environment ORCAN_PROJECT_NAME 2>/dev/null | cut -d= -f2- || true)"
    if [[ -z "${project}" ]]; then
        project="$(tmux show-environment -g ORCAN_PROJECT_NAME 2>/dev/null | cut -d= -f2- || true)"
    fi
    if [[ -n "${project}" && "${project}" != "${session}" ]]; then
        printf '%s#[fg=#0a0e17,bg=#5eead4,bold] %s #[fg=#67e8f9,bg=#164e63,bold] %s #[default] ' \
            "${prefix}" "${project}" "${session}"
    else
        pill "${session}"
        printf ' '
    fi
fi
