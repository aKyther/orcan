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
require_file "install.sh"
require_file "bin/orcan"
require_file "cli/orcan.sh"
require_file "cli/lib/common.sh"
require_file "cli/lib/log.sh"
require_file "cli/lib/paths.sh"
require_file "cli/lib/deps.sh"
require_file "cli/lib/compose.sh"
require_file "cli/lib/git.sh"
require_file "cli/lib/image.sh"
require_file "cli/commands/init.sh"
require_file "cli/commands/sync.sh"
require_file "cli/commands/up.sh"
require_file "cli/commands/build.sh"
require_file "cli/commands/pull.sh"
require_file "cli/commands/publish.sh"
require_file "cli/commands/doctor.sh"
require_file "cli/commands/update.sh"
require_file "cli/commands/uninstall.sh"
require_file "cli/commands/context.sh"
require_file "cli/commands/enter.sh"
require_file "VERSION"
require_file "CHANGELOG.md"
require_file "requirements-docs.txt"
require_file "CONTRIBUTING.md"
require_file "AGENTS.md"
require_file "orcan.config.example.json"
require_file "orcan.config.schema.json"
require_file "docs/STYLE_GUIDE.md"
require_file "tests/host/run.sh"
require_file "tests/host/test_config_io.py"
require_file "tests/host/test_apply_config.py"
require_file "tests/host/test_version.py"
require_file "scripts/repository/config-scaffold.py"
require_file "scripts/repository/config-show.py"
require_file "scripts/repository/config-wizard.py"
require_file "scripts/repository/context_tui.py"
require_file "scripts/repository/wizard_ui.py"
require_file "scripts/repository/settings-wizard.py"
require_file "cli/commands/settings.sh"
require_file "tests/host/test_config_wizard.py"
require_file "tests/host/test_wizard_ui.py"
require_file "tests/host/test_settings_wizard.py"
require_file "scripts/repository/config_io.py"
require_file "scripts/repository/git_worktrees.py"
require_file "scripts/repository/managed_workspace.py"
require_file "tests/host/test_git_worktrees.py"
require_file "scripts/repository/claude_hook.py"
require_file "tests/host/test_claude_hook.py"
require_file "scripts/repository/python.sh"
require_file "scripts/repository/release.sh"
require_file "scripts/repository/check-product-name.sh"
require_file "scripts/repository/docs-mike.sh"
require_file "scripts/migrations/README.md"
require_file "scripts/migrations/flatten-orcan-home.sh"
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
require_file "docker/rootfs/usr/local/bin/init-claude-home"
require_file "docker/rootfs/usr/local/bin/orcan-prompt-clean"
require_file "docker/rootfs/opt/claude-defaults/agents/prompt-refiner.md"
require_file "docker/rootfs/opt/claude-defaults/commands/do.md"
require_file "docker/rootfs/usr/local/bin/init-ai-statusline"
require_file "docker/rootfs/usr/local/bin/orcan-ai-statusline"
require_file "docker/rootfs/usr/local/bin/cursor-init-project"
require_file "docker/rootfs/usr/local/bin/orcan-init-projects"
require_file "docker/rootfs/usr/local/bin/orcan-session-brief"
require_file "docker/rootfs/usr/local/bin/orcan-workspaces"
require_file "docker/rootfs/usr/local/bin/orcan-context-status"
require_file "docker/rootfs/usr/local/lib/orcan/workspaces.py"
require_file "docker/rootfs/opt/cursor-defaults/templates/workspace/session-brief.md"
require_file "docker/rootfs/etc/skel/.zshrc"
require_file "docker/rootfs/etc/skel/.zshrc.d/50-orcan-shell.zsh"
require_file "docker/rootfs/etc/skel/.zshrc.d/55-orcan-devtools.zsh"
require_file "docker/rootfs/etc/skel/.zshrc.d/70-plugins.zsh"
require_file "docker/rootfs/etc/skel/.zshrc.d/80-starship.zsh"
require_file "docker/rootfs/opt/orcan/gitconfig"
require_file "docker/rootfs/opt/orcan/starship.toml"
require_file "docker/rootfs/opt/orcan/lazygit-config.yml"
require_file "docs/en/guides/terminal-ui.md"
require_file "docs/pl/guides/terminal-ui.md"
require_file "docker/rootfs/etc/orcan/shell/aliases.sh"
require_file "docker/rootfs/etc/orcan/shell/devtools-env.sh"
require_file "docker/rootfs/etc/profile.d/orcan-devtools.sh"
require_file "docker/rootfs/usr/local/bin/cursor-ttyd"
require_file "docker/rootfs/usr/local/bin/agent-launcher"
require_file "docker/rootfs/usr/local/bin/cursor-tmux-workspace-attach"
require_file "docker/rootfs/usr/local/bin/cursor-tmux-bootstrap-workspaces"
require_file "docker/rootfs/usr/local/bin/init-workspace"
require_file "docker/rootfs/etc/tmux/tmux.conf"
require_file "docker/rootfs/etc/tmux/scripts/status-left.sh"
require_file "docker/rootfs/etc/tmux/scripts/status-right.sh"
require_file "docker/rootfs/etc/tmux/scripts/pane-border-right.sh"
require_file "docker/rootfs/etc/tmux/scripts/ai-usage.sh"
require_file "docker/rootfs/etc/skel/.tmux.conf"
require_file "docker/rootfs/etc/skel/.vimrc"
require_file "docker/rootfs/etc/skel/.bashrc.d/50-orcan-shell.sh"
require_file "docker/rootfs/etc/skel/.bashrc.d/55-orcan-devtools.sh"
require_file "docker/rootfs/etc/skel/.bashrc.d/60-orcan-aliases.sh"
require_file "docker/rootfs/etc/orcan/shell/aliases.sh"
require_file "docker/rootfs/opt/cursor-defaults/templates/cursorignore"
require_file "docker/rootfs/opt/cursor-defaults/templates/cursorindexingignore"
require_file "docker/rootfs/opt/cursor-defaults/templates/claudeignore"
require_file "docker/rootfs/opt/cursor-defaults/templates/claude/settings.json"

for script in \
    docker/rootfs/usr/local/bin/docker-entrypoint \
    docker/rootfs/usr/local/bin/init-cursor-home \
    docker/rootfs/usr/local/bin/cursor-init-project \
    docker/rootfs/usr/local/bin/orcan-init-projects \
    docker/rootfs/usr/local/bin/orcan-session-brief \
    docker/rootfs/usr/local/bin/cursor-ttyd \
    docker/rootfs/usr/local/bin/agent-launcher \
    docker/rootfs/usr/local/bin/cursor-tmux-workspace-attach \
    docker/rootfs/usr/local/bin/cursor-tmux-bootstrap-workspaces \
    docker/rootfs/usr/local/bin/init-workspace \
    docker/rootfs/usr/local/bin/init-claude-home \
    docker/rootfs/etc/tmux/scripts/status-left.sh \
    docker/rootfs/etc/tmux/scripts/status-right.sh \
    docker/rootfs/etc/tmux/scripts/pane-border-right.sh \
    docker/rootfs/etc/tmux/scripts/window-name.sh \
    docker/rootfs/etc/tmux/scripts/copy-path.sh \
    docker/rootfs/etc/tmux/scripts/session-switch.sh \
    docker/rootfs/etc/tmux/scripts/pick-url.sh \
    scripts/repository/update-env.sh \
    scripts/repository/python.sh \
    scripts/repository/validate-project-dir.sh \
    scripts/repository/require-generated.sh \
    scripts/repository/print-workspace-manifest.sh \
    scripts/repository/registry.sh \
    scripts/repository/release.sh \
    scripts/repository/check-product-name.sh \
    scripts/repository/docs-mike.sh \
    scripts/repository/validate.sh \
    scripts/migrations/flatten-orcan-home.sh \
    install.sh \
    bin/orcan \
    cli/orcan.sh \
    cli/lib/image.sh \
    cli/commands/build.sh \
    cli/commands/pull.sh \
    cli/commands/publish.sh \
    cli/commands/context.sh \
    cli/commands/enter.sh \
    cli/commands/settings.sh \
    tests/smoke/test-container.sh \
    tests/integration/test-path-parity.sh
do
    if [[ -f "${script}" ]]; then
        bash -n "${script}"
        printf 'Syntax OK: %s\n' "${script}"
    fi
done

for script in \
    docker/rootfs/usr/local/bin/orcan-ai-statusline \
    docker/rootfs/usr/local/bin/init-ai-statusline \
    docker/rootfs/usr/local/bin/orcan-workspaces \
    docker/rootfs/usr/local/bin/orcan-context-status \
    docker/rootfs/usr/local/bin/orcan-prompt-clean \
    docker/rootfs/usr/local/lib/orcan/workspaces.py \
    docker/rootfs/etc/tmux/scripts/ai-usage.sh \
    scripts/repository/config-scaffold.py \
    scripts/repository/config-show.py \
    scripts/repository/config-wizard.py \
    scripts/repository/context_tui.py \
    scripts/repository/wizard_ui.py \
    scripts/repository/settings-wizard.py \
    scripts/repository/config_io.py \
    scripts/repository/git_worktrees.py \
    scripts/repository/managed_workspace.py \
    scripts/repository/apply-config.py
do
    if [[ -f "${script}" ]]; then
        PYTHONPATH="${ROOT_DIR}/docker/rootfs/usr/local/lib${PYTHONPATH:+:$PYTHONPATH}" \
            python3 -c "import ast, pathlib; ast.parse(pathlib.Path('${script}').read_text(encoding='utf-8'))"
        printf 'Syntax OK: %s\n' "${script}"
    fi
done

if [[ -f VERSION ]]; then
    ver="$(tr -d '[:space:]' < VERSION)"
    if [[ ! "${ver}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        printf 'VERSION must be SemVer X.Y.Z (got: %s)\n' "${ver}" >&2
        fail=1
    else
        printf 'VERSION OK: %s\n' "${ver}"
    fi
fi

if ! ./scripts/repository/check-product-name.sh; then
    fail=1
fi

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    PROJECT_DIR="${ROOT_DIR}" ./scripts/repository/update-env.sh >/dev/null
    compose_base=(docker compose --project-name orcan)
    "${compose_base[@]}" -f docker-compose.yml -f mounts/compose-projects.generated.yml config --quiet
    "${compose_base[@]}" -f docker-compose.yml -f mounts/compose-projects.generated.yml -f docker-compose.docker.yml config --quiet
    "${compose_base[@]}" -f docker-compose.yml -f mounts/compose-projects.generated.yml -f docker-compose.ttyd.yml config --quiet
    "${compose_base[@]}" -f docker-compose.yml -f mounts/compose-projects.generated.yml -f docker-compose.ttyd.yml -f docker-compose.docker.yml config --quiet
    # Optional --with-git overlay (generated on demand; stub for config check)
    mkdir -p mounts
    cat >mounts/compose-git.generated.yml <<'YAML'
# validate stub — real overlay is written by: orcan up --with-git
services:
  orcan:
    environment:
      ORCAN_WITH_GIT_STUB: "1"
YAML
    "${compose_base[@]}" -f docker-compose.yml -f mounts/compose-projects.generated.yml -f mounts/compose-git.generated.yml -f docker-compose.ttyd.yml config --quiet
    # Optional --with-network overlay (generated on demand; stub for config check)
    cat >mounts/compose-network.generated.yml <<'YAML'
# validate stub — real overlay is written by: orcan up --with-network NAME
services:
  orcan:
    networks:
      - default
      - orcan_ext
networks:
  orcan_ext:
    name: orcan-validate-stub-net
    external: true
YAML
    "${compose_base[@]}" -f docker-compose.yml -f mounts/compose-projects.generated.yml -f mounts/compose-network.generated.yml -f docker-compose.ttyd.yml config --quiet
    resolved="$("${compose_base[@]}" -f docker-compose.yml -f mounts/compose-projects.generated.yml config)"
    if ! printf '%s\n' "${resolved}" | grep -qE 'container_name:[[:space:]]*orcan-1'; then
        printf 'Error: expected container_name orcan-1 in compose config\n' >&2
        fail=1
    else
        printf 'Compose config OK\n'
    fi
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
