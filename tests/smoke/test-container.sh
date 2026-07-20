#!/usr/bin/env bash
# Smoke-test the built cursor-dev image.
# Host-only helper. Requires Docker.

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

COMPOSE=(docker compose -f docker-compose.yml)

printf 'Running container smoke checks...\n'

"${COMPOSE[@]}" run --rm --no-TTY --name cursor-dev-smoke cursor bash -lc '
set -euo pipefail

command -v docker-entrypoint >/dev/null
command -v init-cursor-home >/dev/null
command -v cursor-init-project >/dev/null
command -v cursor-sshd >/dev/null
test -x /usr/sbin/sshd
test -f /etc/ssh/sshd_config.d/cursor.conf
test -d /opt/cursor-defaults
test -d "${HOME}/.cursor"
test -f "${HOME}/.cursor/cli-config.json"
test -f "${HOME}/.tmux.conf"
test -f "${HOME}/.vimrc"
test -r /opt/cursor-defaults/cli-config.json
test ! -w /opt/cursor-defaults/cli-config.json
test -f /opt/cursor-defaults/rules/operating-principles.mdc
test -f "${HOME}/.cursor/rules/operating-principles.mdc"
test -f "${HOME}/.cursor/skills/repository-analysis/SKILL.md"

# Idempotent home init
init-cursor-home | tee /tmp/init1.txt
init-cursor-home | tee /tmp/init2.txt
grep -q "created: 0" /tmp/init2.txt

# Startup must not modify /workspace project files automatically.
# (bind-mount contents vary by host; only assert init-project is explicit.)
cursor-init-project --help >/dev/null
cursor-init-project --dry-run /tmp >/dev/null || true

mkdir -p /tmp/smoke-project
cursor-init-project --dry-run /tmp/smoke-project | grep -q "Create\\|Skipped\\|dry-run"
cursor-init-project /tmp/smoke-project >/dev/null
test -f /tmp/smoke-project/AGENTS.md

printf "SMOKE_OK\n"
'

printf 'Smoke tests passed\n'
