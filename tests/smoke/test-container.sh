#!/usr/bin/env bash
# Smoke-test the built cind image.
# Host-only helper. Requires Docker.

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

# shellcheck source=../../scripts/repository/validate-project-dir.sh
source "${ROOT_DIR}/scripts/repository/validate-project-dir.sh"

validate_project_dir
SMOKE_PROJECT="${PROJECT_DIR}"

COMPOSE=(docker compose -f docker-compose.yml -f .cind/compose-projects.generated.yml)

printf 'Running container smoke checks (PROJECT_DIR=%s)...\n' "${SMOKE_PROJECT}"

"${COMPOSE[@]}" run --rm --no-TTY --name cind-smoke cind bash -lc "
set -euo pipefail

command -v docker-entrypoint >/dev/null
command -v init-cursor-home >/dev/null
command -v init-ai-statusline >/dev/null
command -v cind-ai-statusline >/dev/null
command -v cursor-init-project >/dev/null
command -v cind-init-projects >/dev/null
command -v cind-session-brief >/dev/null
command -v cind-workspaces >/dev/null
command -v cind-context-status >/dev/null
command -v cursor-ttyd >/dev/null
command -v cursor-launcher >/dev/null
command -v cursor-tmux-workspace-attach >/dev/null
command -v cursor-tmux-bootstrap-workspaces >/dev/null
command -v agent >/dev/null
command -v claude >/dev/null
command -v python3 >/dev/null
command -v python >/dev/null
command -v pip3 >/dev/null
command -v uv >/dev/null
python3 -c 'import json, math, os, pathlib, sys, time'
python -c 'import json, sys; assert sys.version_info >= (3, 11)'
uv --version >/dev/null
agent --version >/dev/null
claude --version >/dev/null
command -v ttyd >/dev/null
command -v tree >/dev/null
command -v yq >/dev/null
command -v curl >/dev/null
test -x /usr/local/bin/ttyd
test -x /usr/local/bin/yq
test -x /usr/local/bin/cursor-launcher
test -x /usr/local/bin/cursor-tmux-workspace-attach
test -x /usr/local/bin/cursor-tmux-bootstrap-workspaces
test -x /usr/local/bin/cind-init-projects
test -x /usr/local/bin/cind-session-brief
test -x /usr/local/bin/cind-workspaces
test -x /usr/local/bin/cind-context-status
test -f /usr/local/lib/cind/workspaces.py
test -f /opt/cursor-defaults/templates/workspace/session-brief.md
test -x /usr/local/bin/cind-ai-statusline
test -x /usr/local/bin/init-ai-statusline
test -f /etc/tmux/tmux.conf
test -x /etc/tmux/scripts/status-left.sh
test -x /etc/tmux/scripts/ai-usage.sh
# AI usage cache (stdlib-only Python hook)
AI_CACHE=\"\${HOME}/.cache/cind-smoke-\$\$\"
mkdir -p \"\${AI_CACHE}\"
printf '%s' '{\"model\":{\"display_name\":\"Sonnet\"},\"context_window\":{\"used_percentage\":12},\"rate_limits\":{\"five_hour\":{\"used_percentage\":3}}}' \
  | CIND_AI_PROVIDER=claude CIND_AI_USAGE_DIR=\"\${AI_CACHE}\" cind-ai-statusline | grep -q 'ctx 12%'
test -f \"\${AI_CACHE}/ai-usage-claude.json\"
CIND_AI_USAGE_DIR=\"\${AI_CACHE}\" /etc/tmux/scripts/ai-usage.sh | grep -q 'ctx 12%'
rm -rf \"\${AI_CACHE}\"
# statusLine seed (missing-only)
init-ai-statusline >/tmp/ai-statusline-init.txt
grep -q 'statusLine' \"\${HOME}/.claude/settings.json\"
# Launcher exits cleanly on q
printf 'q\n' | cursor-launcher >/tmp/launcher-out.txt
grep -q 'cind workspaces' /tmp/launcher-out.txt
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

SMOKE_DIR=\"${SMOKE_PROJECT}/.cind-smoke-\$\$\"
mkdir -p \"\${SMOKE_DIR}\"
cursor-init-project --dry-run \"\${SMOKE_DIR}\" > /tmp/init-project-dry.txt
grep -q 'Create\\|Skipped\\|dry-run' /tmp/init-project-dry.txt
cursor-init-project \"\${SMOKE_DIR}\" >/dev/null
test -f \"\${SMOKE_DIR}/AGENTS.md\"
rm -rf \"\${SMOKE_DIR}\"

# tmux workspace bootstrap (no attach)
tmux kill-session -t smoke-test 2>/dev/null || true
CIND_TMUX_ATTACH=0 cursor-tmux-workspace-attach smoke-test \"\${WORKSPACE_ROOT:-${SMOKE_PROJECT}}\" \"\${WORKSPACE_NAME:-cind}\" >/dev/null
tmux -f \"\${HOME}/.tmux.conf\" has-session -t smoke-test
test \"\$(tmux -f \"\${HOME}/.tmux.conf\" list-windows -t smoke-test | wc -l)\" -eq 3
tmux -f \"\${HOME}/.tmux.conf\" list-windows -t smoke-test | grep -q 'tab-1'
tmux -f \"\${HOME}/.tmux.conf\" kill-session -t smoke-test

printf 'SMOKE_OK\n'
"

printf 'Smoke tests passed\n'
