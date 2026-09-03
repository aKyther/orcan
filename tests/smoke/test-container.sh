#!/usr/bin/env bash
# Smoke-test the built orcan image.
# Host-only helper. Requires Docker.

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"
ORCAN_HOME="${ORCAN_HOME:-${ROOT_DIR}}"

# shellcheck source=../../scripts/repository/validate-project-dir.sh
source "${ROOT_DIR}/scripts/repository/validate-project-dir.sh"

validate_project_dir
SMOKE_PROJECT="${PROJECT_DIR}"

COMPOSE_PROJECTS_FILE="${ORCAN_COMPOSE_PROJECTS:-${ORCAN_HOME}/mounts/compose-projects.generated.yml}"
COMPOSE=(docker compose --env-file "${ORCAN_HOME}/.env" -f docker-compose.yml -f "${COMPOSE_PROJECTS_FILE}")

printf 'Running container smoke checks (PROJECT_DIR=%s)...\n' "${SMOKE_PROJECT}"

"${COMPOSE[@]}" run --rm --no-TTY --name orcan-smoke orcan bash -lc "
set -euo pipefail

command -v docker-entrypoint >/dev/null
command -v init-cursor-home >/dev/null
command -v init-ai-statusline >/dev/null
command -v orcan-ai-statusline >/dev/null
command -v cursor-init-project >/dev/null
command -v orcan-init-projects >/dev/null
command -v orcan-session-brief >/dev/null
command -v orcan-workspaces >/dev/null
command -v orcan-context-status >/dev/null
command -v cursor-ttyd >/dev/null
command -v orcan-supervisord >/dev/null
command -v orcan-supervisor-status >/dev/null
command -v supervisord >/dev/null
command -v agent-launcher >/dev/null
! grep -q '/home/developer/workspaces/\*/orcan/cockpit/src' /usr/local/bin/agent-launcher
command -v cursor-launcher >/dev/null
command -v tmux >/dev/null
tmux -V | grep -Eq '^tmux 3\.[6-9]'
command -v cursor-tmux-workspace-attach >/dev/null
command -v cursor-tmux-bootstrap-workspaces >/dev/null
command -v codex >/dev/null
! command -v gemini >/dev/null
! command -v copilot >/dev/null
command -v python3 >/dev/null
command -v python >/dev/null
command -v pip3 >/dev/null
command -v uv >/dev/null
python3 -c 'import json, math, os, pathlib, sys, time'
python -c 'import json, sys; assert sys.version_info >= (3, 11)'
uv --version >/dev/null
codex --version >/dev/null
python3 -c 'import json; agents = json.load(open(\"/etc/orcan/agents.json\"))[\"agents\"]; assert agents == {\"cursor\": False, \"claude\": False, \"codex\": True, \"gemini\": False, \"copilot\": False}'
command -v ttyd >/dev/null
command -v tree >/dev/null
command -v yq >/dev/null
command -v curl >/dev/null
command -v gh >/dev/null
command -v sg >/dev/null
command -v ast-grep >/dev/null
command -v ssh >/dev/null
command -v rsync >/dev/null
command -v sqlite3 >/dev/null
test -x /usr/local/bin/ttyd
test -x /usr/local/bin/yq
test -x /usr/local/bin/gh
test -x /usr/local/bin/sg
test -x /usr/local/bin/agent-launcher
test -L /usr/local/bin/cursor-launcher
test -x /usr/local/bin/cursor-launcher
test -x /usr/local/bin/cursor-tmux-workspace-attach
test -x /usr/local/bin/cursor-tmux-bootstrap-workspaces
test -x /usr/local/bin/orcan-init-projects
test -x /usr/local/bin/orcan-session-brief
test -x /usr/local/bin/orcan-workspaces
test -x /usr/local/bin/orcan-context-status
test -f /usr/local/lib/orcan/workspaces.py
test -x /opt/orcan-cockpit/venv/bin/python3
test -x /opt/orcan-cockpit/venv/bin/orcan-cockpit
/opt/orcan-cockpit/venv/bin/python3 -c 'import orcan_cockpit, textual, pyte, libtmux, watchfiles'
PYTHONPATH=/usr/local/lib /opt/orcan-cockpit/venv/bin/python3 -c 'from orcan import agent_executor, agent_inbox, workspaces; from orcan_cockpit import app, cli, picker, session_glance'
test -f /opt/cursor-defaults/templates/workspace/session-brief.md
test -x /usr/local/bin/orcan-ai-statusline
test -x /usr/local/bin/init-ai-statusline
test -f /etc/tmux/tmux.conf
test -x /etc/tmux/scripts/status-left.sh
test -x /etc/tmux/scripts/ai-usage.sh
# AI usage cache (stdlib-only Python hook)
AI_CACHE=\"\${HOME}/.cache/orcan-smoke-\$\$\"
mkdir -p \"\${AI_CACHE}\"
printf '%s' '{\"model\":{\"display_name\":\"Sonnet\"},\"context_window\":{\"used_percentage\":12},\"rate_limits\":{\"five_hour\":{\"used_percentage\":3}}}' \
  | ORCAN_AI_PROVIDER=claude ORCAN_AI_USAGE_DIR=\"\${AI_CACHE}\" orcan-ai-statusline | grep -q 'ctx 12%'
test -f \"\${AI_CACHE}/ai-usage-claude.json\"
ORCAN_AI_USAGE_DIR=\"\${AI_CACHE}\" /etc/tmux/scripts/ai-usage.sh | grep -Eq 'claude.*12%.*3%'
rm -rf \"\${AI_CACHE}\"
# statusLine seed (missing-only)
init-ai-statusline >/tmp/ai-statusline-init.txt
grep -q 'statusLine' \"\${HOME}/.claude/settings.json\"
# A stale checkout beside the active workspace must not shadow the image's
# cockpit package (regression for workspace-glob PYTHONPATH discovery).
mkdir -p /home/developer/workspaces/orcan-smoke-stale/orcan/cockpit/src/orcan_cockpit
printf '%s\n' invalid >/home/developer/workspaces/orcan-smoke-stale/orcan/cockpit/src/orcan_cockpit/__init__.py
# Launcher exits cleanly on q with its default, image-owned import path.
printf 'q\n' | env -u PYTHONPATH agent-launcher >/tmp/launcher-out.txt
grep -q 'orcan workspaces' /tmp/launcher-out.txt
rm -rf /home/developer/workspaces/orcan-smoke-stale
test -d /opt/cursor-defaults
test -d \"\${HOME}/.cursor\"
test -f \"\${HOME}/.cursor/cli-config.json\"
test -f \"\${HOME}/.tmux.conf\"
test -L \"\${HOME}/.config/tmux\"
test -f \"\${HOME}/.vimrc\"
test -r /opt/cursor-defaults/cli-config.json
test ! -w /opt/cursor-defaults/cli-config.json
test -f /opt/cursor-defaults/rules/operating-principles.mdc
test -f \"\${HOME}/.cursor/rules/operating-principles.mdc\"
test -f \"\${HOME}/.cursor/skills/repository-analysis/SKILL.md\"

test \"\$(pwd -P)\" = \"\${WORKSPACE_ROOT:-${SMOKE_PROJECT}}\"
test \"\${PROJECT_DIR}\" = \"${SMOKE_PROJECT}\"
test -d \"\${PROJECT_DIR}\"

# Workspace agent seeds (written by init-workspace at entrypoint)
if [[ -n \"\${WORKSPACE_ROOT:-}\" && -d \"\${WORKSPACE_ROOT}\" ]]; then
  test -f \"\${WORKSPACE_ROOT}/.manifest.json\"
  test -f \"\${WORKSPACE_ROOT}/AGENTS.md\"
  test -f \"\${WORKSPACE_ROOT}/CLAUDE.md\"
  grep -q 'Read first' \"\${WORKSPACE_ROOT}/AGENTS.md\"
  grep -q 'Think before coding' \"\${WORKSPACE_ROOT}/AGENTS.md\"
fi

# Idempotent home init
init-cursor-home > /tmp/init1.txt
init-cursor-home > /tmp/init2.txt
grep -q 'created: 0' /tmp/init2.txt

# Startup must not modify the mounted project automatically.
cursor-init-project --help >/dev/null

SMOKE_DIR=\"${SMOKE_PROJECT}/.orcan-smoke-\$\$\"
mkdir -p \"\${SMOKE_DIR}\"
cursor-init-project --dry-run \"\${SMOKE_DIR}\" > /tmp/init-project-dry.txt
grep -q 'Create\\|Skipped\\|dry-run' /tmp/init-project-dry.txt
cursor-init-project \"\${SMOKE_DIR}\" >/dev/null
test -f \"\${SMOKE_DIR}/AGENTS.md\"
rm -rf \"\${SMOKE_DIR}\"

# tmux workspace bootstrap (no attach)
tmux kill-session -t smoke-test 2>/dev/null || true
ORCAN_TMUX_ATTACH=0 cursor-tmux-workspace-attach smoke-test \"\${WORKSPACE_ROOT:-${SMOKE_PROJECT}}\" \"\${WORKSPACE_NAME:-orcan}\" >/dev/null
tmux -f \"\${HOME}/.tmux.conf\" has-session -t smoke-test
test \"\$(tmux -f \"\${HOME}/.tmux.conf\" list-windows -t smoke-test | wc -l)\" -eq 3
tmux -f \"\${HOME}/.tmux.conf\" list-windows -t smoke-test | grep -q 'tab-1'
tmux -f \"\${HOME}/.tmux.conf\" kill-session -t smoke-test

printf 'SMOKE_OK\n'
"

printf 'Smoke tests passed\n'
