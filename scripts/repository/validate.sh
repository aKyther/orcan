#!/usr/bin/env bash
# Validate repository layout and shell script syntax.
# Host-only: do not copy this into the Docker image.

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

fail=0

require_file() {
    local path="$1"
    if [[ ! -e "${path}" ]]; then
        printf 'Missing: %s\n' "${path}" >&2
        fail=1
    fi
}

require_file "Dockerfile"
require_file "docker-compose.yml"
require_file "docker-compose.docker.yml"
require_file "docker-compose.ttyd.yml"
require_file "Makefile"
require_file "scripts/repository/config-scaffold.py"
require_file "scripts/repository/config-show.py"
require_file "cind.config.example.json"
require_file "docker/rootfs/opt/cursor-defaults/cli-config.json"
require_file "docker/rootfs/opt/cursor-defaults/rules/operating-principles.mdc"
require_file "docker/rootfs/opt/cursor-defaults/rules/karpathy-guidelines.mdc"
require_file "docker/rootfs/opt/cursor-defaults/rules/planning-and-execution.mdc"
require_file "docker/rootfs/opt/cursor-defaults/rules/code-quality.mdc"
require_file "docker/rootfs/opt/cursor-defaults/rules/documentation-discipline.mdc"
require_file "docker/rootfs/opt/cursor-defaults/rules/container-safety.mdc"
require_file "docker/rootfs/opt/cursor-defaults/skills/repository-analysis/SKILL.md"
require_file "docker/rootfs/opt/cursor-defaults/skills/focused-implementation/SKILL.md"
require_file "docker/rootfs/opt/cursor-defaults/skills/final-review/SKILL.md"
require_file "docker/rootfs/usr/local/bin/docker-entrypoint"
require_file "docker/rootfs/usr/local/bin/init-cursor-home"
require_file "docker/rootfs/usr/local/bin/init-ai-statusline"
require_file "docker/rootfs/usr/local/bin/cind-ai-statusline"
require_file "docker/rootfs/usr/local/bin/cursor-init-project"
require_file "docker/rootfs/usr/local/bin/cind-init-projects"
require_file "docker/rootfs/usr/local/bin/cind-session-brief"
require_file "docker/rootfs/usr/local/bin/cind-workspaces"
require_file "docker/rootfs/usr/local/bin/cind-context-status"
require_file "docker/rootfs/usr/local/lib/cind/workspaces.py"
require_file "docker/rootfs/opt/cursor-defaults/templates/workspace/session-brief.md"
require_file "cind.config.example.yaml"
require_file "requirements-host.txt"
require_file "scripts/repository/config-wizard.py"
require_file "scripts/repository/config_io.py"
require_file "scripts/repository/python.sh"

require_file "docker/rootfs/etc/skel/.zshrc"
require_file "docker/rootfs/etc/skel/.zshrc.d/50-cind-shell.zsh"
require_file "docker/rootfs/etc/skel/.zshrc.d/70-plugins.zsh"
require_file "docker/rootfs/etc/skel/.zshrc.d/80-starship.zsh"
require_file "docker/rootfs/opt/cind/gitconfig"
require_file "docker/rootfs/opt/cind/starship.toml"
require_file "docker/rootfs/etc/cind/shell/aliases.sh"
require_file "docker/rootfs/usr/local/bin/cursor-ttyd"
require_file "docker/rootfs/usr/local/bin/cursor-launcher"
require_file "docker/rootfs/usr/local/bin/cursor-tmux-workspace-attach"
require_file "docker/rootfs/usr/local/bin/cursor-tmux-bootstrap-workspaces"
require_file "docker/rootfs/usr/local/bin/init-workspace"
require_file "docker/rootfs/etc/tmux/tmux.conf"
require_file "docker/rootfs/etc/tmux/scripts/status-left.sh"
require_file "docker/rootfs/etc/tmux/scripts/status-right.sh"
require_file "docker/rootfs/etc/tmux/scripts/ai-usage.sh"
require_file "docker/rootfs/etc/skel/.tmux.conf"
require_file "docker/rootfs/etc/skel/.vimrc"
require_file "docker/rootfs/etc/skel/.bashrc.d/50-cind-shell.sh"
require_file "docker/rootfs/etc/skel/.bashrc.d/60-cind-aliases.sh"
require_file "docker/rootfs/etc/cind/shell/aliases.sh"
require_file "docker/rootfs/opt/cursor-defaults/templates/cursorignore"
require_file "docker/rootfs/opt/cursor-defaults/templates/cursorindexingignore"
require_file "docker/rootfs/opt/cursor-defaults/templates/claudeignore"
require_file "docker/rootfs/opt/cursor-defaults/templates/claude/settings.json"

for script in \
    docker/rootfs/usr/local/bin/docker-entrypoint \
    docker/rootfs/usr/local/bin/init-cursor-home \
    docker/rootfs/usr/local/bin/cursor-init-project \
    docker/rootfs/usr/local/bin/cind-init-projects \
    docker/rootfs/usr/local/bin/cind-session-brief \
    docker/rootfs/usr/local/bin/cursor-ttyd \
    docker/rootfs/usr/local/bin/cursor-launcher \
    docker/rootfs/usr/local/bin/cursor-tmux-workspace-attach \
    docker/rootfs/usr/local/bin/cursor-tmux-bootstrap-workspaces \
    docker/rootfs/usr/local/bin/init-workspace \
    docker/rootfs/etc/tmux/scripts/status-left.sh \
    docker/rootfs/etc/tmux/scripts/status-right.sh \
    docker/rootfs/etc/tmux/scripts/window-name.sh \
    docker/rootfs/etc/tmux/scripts/copy-path.sh \
    docker/rootfs/etc/tmux/scripts/session-switch.sh \
    scripts/repository/update-env.sh \
    scripts/repository/python.sh \
    scripts/repository/validate-project-dir.sh \
    scripts/repository/require-generated.sh \
    scripts/repository/print-workspace-manifest.sh \
    scripts/repository/registry.sh \
    scripts/repository/validate.sh \
    tests/smoke/test-container.sh \
    tests/integration/test-path-parity.sh
do
    if [[ -f "${script}" ]]; then
        bash -n "${script}"
        printf 'Syntax OK: %s\n' "${script}"
    fi
done

for script in \
    docker/rootfs/usr/local/bin/cind-ai-statusline \
    docker/rootfs/usr/local/bin/init-ai-statusline \
    docker/rootfs/usr/local/bin/cind-workspaces \
    docker/rootfs/usr/local/bin/cind-context-status \
    docker/rootfs/usr/local/lib/cind/workspaces.py \
    docker/rootfs/etc/tmux/scripts/ai-usage.sh \
    scripts/repository/config-scaffold.py \
    scripts/repository/config-show.py \
    scripts/repository/config-wizard.py \
    scripts/repository/config_io.py \
    scripts/repository/apply-config.py
do
    if [[ -f "${script}" ]]; then
        PYTHONPATH="${ROOT_DIR}/docker/rootfs/usr/local/lib${PYTHONPATH:+:$PYTHONPATH}" \
            python3 -m py_compile "${script}"
        printf 'Syntax OK: %s\n' "${script}"
    fi
done

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    PROJECT_DIR="${ROOT_DIR}" ./scripts/repository/update-env.sh >/dev/null
    docker compose -f docker-compose.yml -f .cind/compose-projects.generated.yml config --quiet
    docker compose -f docker-compose.yml -f .cind/compose-projects.generated.yml -f docker-compose.docker.yml config --quiet
    docker compose -f docker-compose.yml -f .cind/compose-projects.generated.yml -f docker-compose.ttyd.yml config --quiet
    docker compose -f docker-compose.yml -f .cind/compose-projects.generated.yml -f docker-compose.ttyd.yml -f docker-compose.docker.yml config --quiet
    printf 'Compose config OK\n'
else
    printf 'Skip: Docker daemon not available for compose config\n'
fi

# Stale path check (ignore this script's own pattern list)
stale=0
for pattern in \
    'scripts/init-cursor-home.sh' \
    'scripts/docker-entrypoint.sh' \
    'scripts/init-project.sh' \
    'cursor-home/' \
    'cursor-sshd' \
    'docker-compose.ssh.yml' \
    'cursor-tmux-attach' \
    'Named volumes' \
    'cursor-cli-devcontainer' \
    'TMUX_SESSION_NAME' \
    'make terminal PROJECT_DIR=' \
    'cursor-app-config'
do
    if grep -R --exclude-dir=.git --exclude-dir=site --exclude='validate.sh' -n "${pattern}" . \
        > /tmp/stale-hits.txt 2>/dev/null; then
        if [[ -s /tmp/stale-hits.txt ]]; then
            printf 'Stale references to %s:\n' "${pattern}" >&2
            cat /tmp/stale-hits.txt >&2
            stale=1
        fi
    fi
done

if (( stale )); then
    fail=1
fi

if (( fail )); then
    printf 'Validation failed\n' >&2
    exit 1
fi

printf 'Repository validation passed\n'
