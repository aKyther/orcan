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
require_file "scripts/repository/validate-project-dir.sh"
require_file "docker/rootfs/opt/cursor-defaults/cli-config.json"
require_file "docker/rootfs/opt/cursor-defaults/rules/operating-principles.mdc"
require_file "docker/rootfs/opt/cursor-defaults/rules/planning-and-execution.mdc"
require_file "docker/rootfs/opt/cursor-defaults/rules/code-quality.mdc"
require_file "docker/rootfs/opt/cursor-defaults/rules/documentation-discipline.mdc"
require_file "docker/rootfs/opt/cursor-defaults/rules/container-safety.mdc"
require_file "docker/rootfs/opt/cursor-defaults/skills/repository-analysis/SKILL.md"
require_file "docker/rootfs/opt/cursor-defaults/skills/focused-implementation/SKILL.md"
require_file "docker/rootfs/opt/cursor-defaults/skills/final-review/SKILL.md"
require_file "docker/rootfs/usr/local/bin/docker-entrypoint"
require_file "docker/rootfs/usr/local/bin/init-cursor-home"
require_file "docker/rootfs/usr/local/bin/cursor-init-project"
require_file "docker/rootfs/usr/local/bin/cursor-ttyd"
require_file "docker/rootfs/etc/skel/.tmux.conf"
require_file "docker/rootfs/etc/skel/.vimrc"
require_file "docker/rootfs/etc/skel/.bashrc.d/50-cursor-dev.sh"
require_file "docker/rootfs/etc/profile.d/cursor-dev-path.sh"

for script in \
    docker/rootfs/usr/local/bin/docker-entrypoint \
    docker/rootfs/usr/local/bin/init-cursor-home \
    docker/rootfs/usr/local/bin/cursor-init-project \
    docker/rootfs/usr/local/bin/cursor-ttyd \
    scripts/repository/update-env.sh \
    scripts/repository/validate-project-dir.sh \
    scripts/repository/validate.sh \
    tests/smoke/test-container.sh \
    tests/integration/test-path-parity.sh
do
    if [[ -f "${script}" ]]; then
        bash -n "${script}"
        printf 'Syntax OK: %s\n' "${script}"
    fi
done

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    PROJECT_DIR="${ROOT_DIR}" ./scripts/repository/update-env.sh >/dev/null
    docker compose -f docker-compose.yml config --quiet
    docker compose -f docker-compose.yml -f docker-compose.docker.yml config --quiet
    docker compose -f docker-compose.yml -f docker-compose.ttyd.yml config --quiet
    docker compose -f docker-compose.yml -f docker-compose.ttyd.yml -f docker-compose.docker.yml config --quiet
    printf 'Compose config OK\n'
else
    printf 'Skip: Docker daemon not available for compose config\n'
fi

# Stale path check (ignore this script's own pattern list)
stale=0
for pattern in 'scripts/init-cursor-home.sh' 'scripts/docker-entrypoint.sh' 'scripts/init-project.sh' 'cursor-home/' 'cursor-sshd' 'docker-compose.ssh.yml'; do
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
