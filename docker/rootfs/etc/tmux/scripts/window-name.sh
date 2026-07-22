#!/usr/bin/env bash
# Set a meaningful window name with optional unicode icon.
# Usage: window-name.sh [window_id]
set -Eeuo pipefail

wid="${1:-}"
if [[ -z "${wid}" ]]; then
    wid="$(tmux display -p '#{window_id}' 2>/dev/null || true)"
fi
[[ -n "${wid}" ]] || exit 0

current="$(tmux display -p -t "${wid}" '#{window_name}' 2>/dev/null || true)"
# Already has leading icon (non-ASCII first char)
if [[ "${current}" =~ ^[^[:ascii:]] ]]; then
    exit 0
fi

pane_path="$(tmux display -p -t "${wid}" '#{pane_current_path}' 2>/dev/null || pwd)"
base="$(basename "${pane_path}")"
cmd="$(tmux display -p -t "${wid}" '#{pane_current_command}' 2>/dev/null || true)"

icon=""
label="${current}"

case "${current,,}" in
    editor|edit|code) icon="📝"; label="editor" ;;
    server|api|backend) icon="🐍"; label="server" ;;
    frontend|web|ui) icon="🌐"; label="frontend" ;;
    database|db|postgres|mysql) icon="🗄"; label="database" ;;
    docs|doc|documentation) icon="📖"; label="docs" ;;
    test|tests|spec) icon="🧪"; label="tests" ;;
    log|logs|tail) icon="⚙"; label="logs" ;;
    shell|term|bash) icon="🖥"; label="shell" ;;
    *)
        if [[ -f "${pane_path}/docker-compose.yml" || -f "${pane_path}/compose.yml" ]]; then
            icon="⚙"; label="logs"
        elif [[ -f "${pane_path}/package.json" ]]; then
            icon="🌐"; label="frontend"
        elif [[ -f "${pane_path}/pyproject.toml" || -f "${pane_path}/requirements.txt" ]]; then
            icon="🐍"; label="backend"
        elif [[ -d "${pane_path}/docs" && "${base}" == "docs" ]]; then
            icon="📖"; label="docs"
        elif [[ -d "${pane_path}/tests" || "${base}" == "tests" ]]; then
            icon="🧪"; label="tests"
        elif [[ "${cmd}" =~ ^(bash|sh|zsh|fish)$ ]]; then
            icon="🖥"; label="${base:-shell}"
        else
            icon="📄"; label="${current:-${base:-window}}"
        fi
        ;;
esac

tmux rename-window -t "${wid}" "${icon} ${label}" 2>/dev/null || true
