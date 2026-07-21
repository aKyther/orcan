#!/usr/bin/env bash
# Smoke-test the built cursor-dev image.
# Host-only helper. Requires Docker.

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

# shellcheck source=../../scripts/repository/validate-project-dir.sh
source "${ROOT_DIR}/scripts/repository/validate-project-dir.sh"

validate_project_dir
SMOKE_PROJECT="${PROJECT_DIR}"

COMPOSE=(docker compose -f docker-compose.yml)

printf 'Running container smoke checks (PROJECT_DIR=%s)...\n' "${SMOKE_PROJECT}"

"${COMPOSE[@]}" run --rm --no-TTY --name cursor-dev-smoke cursor bash -lc "
set -euo pipefail

command -v docker-entrypoint >/dev/null
command -v init-cursor-home >/dev/null
command -v cursor-init-project >/dev/null
command -v cursor-ttyd >/dev/null
command -v ttyd >/dev/null
test -x /usr/local/bin/ttyd
test -d /opt/cursor-defaults
test -d \"\${HOME}/.cursor\"
test -f \"\${HOME}/.cursor/cli-config.json\"
test -f \"\${HOME}/.tmux.conf\"
test -f \"\${HOME}/.vimrc\"
test -r /opt/cursor-defaults/cli-config.json
test ! -w /opt/cursor-defaults/cli-config.json
test -f /opt/cursor-defaults/rules/operating-principles.mdc
test -f \"\${HOME}/.cursor/rules/operating-principles.mdc\"
test -f \"\${HOME}/.cursor/skills/repository-analysis/SKILL.md\"

test \"\$(pwd -P)\" = \"${SMOKE_PROJECT}\"
test \"\${PROJECT_DIR}\" = \"${SMOKE_PROJECT}\"
test -d \"\${PROJECT_DIR}\"

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

printf 'SMOKE_OK\n'
"

printf 'Smoke tests passed\n'
