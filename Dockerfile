# syntax=docker/dockerfile:1.7

# ------------------------------------------------------------------------------
# Tool stages
# ------------------------------------------------------------------------------

FROM node:22-bookworm-slim AS node-tools

# No network fetch here — final stage installs pnpm with a pinned version.

FROM golang:1.24-bookworm AS go-tools

FROM rust:1-bookworm AS rust-tools

FROM ghcr.io/astral-sh/uv:latest AS uv-tools

# ------------------------------------------------------------------------------
# Final image
# ------------------------------------------------------------------------------

FROM debian:bookworm-slim

ARG USERNAME=developer
ARG USER_UID=1000
ARG USER_GID=1000
ARG DOCKER_GID=999

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# ------------------------------------------------------------------------------
# Base packages
# ------------------------------------------------------------------------------

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    &&     apt-get install -y --no-install-recommends \
        bash \
        bat \
        build-essential \
        ca-certificates \
        curl \
        fd-find \
        fzf \
        git \
        git-lfs \
        gnupg \
        hyperfine \
        iproute2 \
        jq \
        less \
        make \
        nano \
        net-tools \
        openssh-client \
        parallel \
        postgresql-client \
        python3 \
        python3-dev \
        python3-pip \
        python3-venv \
        python-is-python3 \
        redis-tools \
        ripgrep \
        rsync \
        shellcheck \
        sqlite3 \
        sudo \
        tree \
        tzdata \
        unzip \
        vim \
        wget \
        zip \
        zsh \
        zsh-autosuggestions \
        zsh-syntax-highlighting \
        zstd \
    && ln -sf /usr/bin/fdfind /usr/local/bin/fd \
    && ln -sf /usr/bin/batcat /usr/local/bin/bat \
    && python3 --version \
    && python --version \
    && pip3 --version \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------------------------
# Node.js + npm + pnpm
# ------------------------------------------------------------------------------

ARG PNPM_VERSION=10.12.1

COPY --from=node-tools /usr/local/bin/node /usr/local/bin/node
COPY --from=node-tools /usr/local/lib/node_modules /usr/local/lib/node_modules

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "${arch}" in \
        amd64) pnpm_arch="x64" ;; \
        arm64) pnpm_arch="arm64" ;; \
        *) echo "unsupported architecture for pnpm: ${arch}" >&2; exit 1 ;; \
    esac; \
    ln -sf node /usr/local/bin/nodejs; \
    ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm; \
    ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx; \
    for attempt in 1 2 3; do \
        if curl -fsSL \
            "https://github.com/pnpm/pnpm/releases/download/v${PNPM_VERSION}/pnpm-linuxstatic-${pnpm_arch}" \
            -o /usr/local/bin/pnpm; then \
            break; \
        fi; \
        echo "pnpm download attempt ${attempt} failed, retrying..." >&2; \
        sleep 5; \
    done; \
    test -s /usr/local/bin/pnpm; \
    chmod 0755 /usr/local/bin/pnpm; \
    node --version; \
    npm --version; \
    pnpm --version

# ------------------------------------------------------------------------------
# Go / Rust / uv
# ------------------------------------------------------------------------------

COPY --from=go-tools /usr/local/go /usr/local/go
COPY --from=rust-tools /usr/local/cargo /usr/local/cargo
COPY --from=rust-tools /usr/local/rustup /usr/local/rustup
COPY --from=uv-tools /uv /usr/local/bin/uv
COPY --from=uv-tools /uvx /usr/local/bin/uvx

RUN set -eux; \
    uv --version; \
    uvx --version

# ------------------------------------------------------------------------------
# Docker CLI + Compose + Buildx
# ------------------------------------------------------------------------------

RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
        -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        docker-ce-cli \
        docker-buildx-plugin \
        docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------------------------
# eza
# ------------------------------------------------------------------------------

RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://raw.githubusercontent.com/eza-community/eza/main/deb.asc \
        | gpg --dearmor -o /etc/apt/keyrings/eza.gpg \
    && chmod 0644 /etc/apt/keyrings/eza.gpg \
    && echo \
        "deb [signed-by=/etc/apt/keyrings/eza.gpg] http://deb.gierens.de stable main" \
        > /etc/apt/sources.list.d/eza.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends eza \
    && rm -rf /var/lib/apt/lists/* \
    && eza --version

# ------------------------------------------------------------------------------
# ttyd (browser terminal)
# ------------------------------------------------------------------------------

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "${arch}" in \
        amd64) ttyd_arch="x86_64" ;; \
        arm64) ttyd_arch="aarch64" ;; \
        *) echo "unsupported architecture for ttyd: ${arch}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.${ttyd_arch}" \
        -o /usr/local/bin/ttyd; \
    chmod 0755 /usr/local/bin/ttyd; \
    ttyd --version

# ------------------------------------------------------------------------------
# tmux 3.6a (static musl build — Debian bookworm only ships 3.3a)
# Pane scrollbars + pane-border-lines spaces need >= 3.5 / 3.6.
# ------------------------------------------------------------------------------

ARG TMUX_VERSION=3.6a

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "${arch}" in \
        amd64) tmux_arch="x86_64" ;; \
        arm64) tmux_arch="arm64" ;; \
        *) echo "unsupported architecture for tmux: ${arch}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL \
        "https://github.com/tmux/tmux-builds/releases/download/v${TMUX_VERSION}/tmux-${TMUX_VERSION}-linux-${tmux_arch}.tar.gz" \
        | tar -xz -C /usr/local/bin tmux; \
    chmod 0755 /usr/local/bin/tmux; \
    tmux -V | grep -F "tmux ${TMUX_VERSION}"

# ------------------------------------------------------------------------------
# yq (YAML processor; mikefarah/yq)
# ------------------------------------------------------------------------------

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "${arch}" in \
        amd64) yq_arch="amd64" ;; \
        arm64) yq_arch="arm64" ;; \
        *) echo "unsupported architecture for yq: ${arch}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/mikefarah/yq/releases/download/v4.45.4/yq_linux_${yq_arch}" \
        -o /usr/local/bin/yq; \
    chmod 0755 /usr/local/bin/yq; \
    yq --version

# ------------------------------------------------------------------------------
# gh (GitHub CLI) + ast-grep (structural search) — agents use these on PATH
# ------------------------------------------------------------------------------

ARG GH_VERSION=2.96.0
ARG AST_GREP_VERSION=0.45.0

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "${arch}" in \
        amd64) \
            gh_arch="amd64"; \
            sg_arch="x86_64-unknown-linux-gnu"; \
            ;; \
        arm64) \
            gh_arch="arm64"; \
            sg_arch="aarch64-unknown-linux-gnu"; \
            ;; \
        *) echo "unsupported architecture for gh/ast-grep: ${arch}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${gh_arch}.tar.gz" \
        | tar -xz --strip-components=1 -C /usr/local \
            "gh_${GH_VERSION}_linux_${gh_arch}/bin/gh"; \
    chmod 0755 /usr/local/bin/gh; \
    gh --version; \
    tmp="$(mktemp -d)"; \
    curl -fsSL "https://github.com/ast-grep/ast-grep/releases/download/${AST_GREP_VERSION}/app-${sg_arch}.zip" \
        -o "${tmp}/ast-grep.zip"; \
    unzip -q "${tmp}/ast-grep.zip" -d "${tmp}"; \
    install -m 0755 "${tmp}/sg" /usr/local/bin/sg; \
    if [[ -f "${tmp}/ast-grep" ]]; then \
        install -m 0755 "${tmp}/ast-grep" /usr/local/bin/ast-grep; \
    else \
        ln -sf sg /usr/local/bin/ast-grep; \
    fi; \
    rm -rf "${tmp}"; \
    sg --version; \
    ast-grep --version

# ------------------------------------------------------------------------------
# Starship + delta + lazygit (shell / git UX)
# ------------------------------------------------------------------------------

ARG STARSHIP_VERSION=1.22.1
ARG DELTA_VERSION=0.18.2
ARG LAZYGIT_VERSION=0.48.0

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "${arch}" in \
        amd64) \
            starship_arch="x86_64-unknown-linux-musl"; \
            delta_arch="x86_64-unknown-linux-gnu"; \
            lazygit_arch="Linux_x86_64"; \
            ;; \
        arm64) \
            starship_arch="aarch64-unknown-linux-musl"; \
            delta_arch="aarch64-unknown-linux-gnu"; \
            lazygit_arch="Linux_arm64"; \
            ;; \
        *) echo "unsupported architecture for shell tools: ${arch}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/starship/starship/releases/download/v${STARSHIP_VERSION}/starship-${starship_arch}.tar.gz" \
        | tar -xz -C /usr/local/bin starship; \
    chmod 0755 /usr/local/bin/starship; \
    starship --version; \
    curl -fsSL "https://github.com/dandavison/delta/releases/download/${DELTA_VERSION}/delta-${DELTA_VERSION}-${delta_arch}.tar.gz" \
        | tar -xz --strip-components=1 -C /usr/local/bin "delta-${DELTA_VERSION}-${delta_arch}/delta"; \
    chmod 0755 /usr/local/bin/delta; \
    delta --version; \
    curl -fsSL "https://github.com/jesseduffield/lazygit/releases/download/v${LAZYGIT_VERSION}/lazygit_${LAZYGIT_VERSION}_${lazygit_arch}.tar.gz" \
        | tar -xz -C /usr/local/bin lazygit; \
    chmod 0755 /usr/local/bin/lazygit; \
    lazygit --version

# ------------------------------------------------------------------------------
# shfmt + difftastic (shell formatting; structural diff for reviewing refactors)
# ------------------------------------------------------------------------------

ARG SHFMT_VERSION=3.13.1
ARG DIFFT_VERSION=0.70.0

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "${arch}" in \
        amd64) \
            shfmt_arch="amd64"; \
            difft_arch="x86_64-unknown-linux-gnu"; \
            ;; \
        arm64) \
            shfmt_arch="arm64"; \
            difft_arch="aarch64-unknown-linux-gnu"; \
            ;; \
        *) echo "unsupported architecture for shfmt/difftastic: ${arch}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/mvdan/sh/releases/download/v${SHFMT_VERSION}/shfmt_v${SHFMT_VERSION}_linux_${shfmt_arch}" \
        -o /usr/local/bin/shfmt; \
    chmod 0755 /usr/local/bin/shfmt; \
    shfmt --version; \
    curl -fsSL "https://github.com/Wilfred/difftastic/releases/download/${DIFFT_VERSION}/difft-${difft_arch}.tar.gz" \
        | tar -xz -C /usr/local/bin difft; \
    chmod 0755 /usr/local/bin/difft; \
    difft --version

# ------------------------------------------------------------------------------
# Container filesystem (scripts, defaults, shell configs)
# ------------------------------------------------------------------------------

COPY docker/rootfs/ /

RUN chmod 0755 \
        /usr/local/bin/docker-entrypoint \
        /usr/local/bin/init-cursor-home \
        /usr/local/bin/init-claude-home \
        /usr/local/bin/init-ai-statusline \
        /usr/local/bin/orcan-ai-statusline \
        /usr/local/bin/init-workspace \
        /usr/local/bin/cursor-init-project \
        /usr/local/bin/orcan-init-projects \
        /usr/local/bin/orcan-session-brief \
        /usr/local/bin/orcan-workspaces \
        /usr/local/bin/orcan-context-status \
        /usr/local/bin/orcan-context-propose \
        /usr/local/bin/orcan-context-review \
        /usr/local/bin/orcan-context-reflect \
        /usr/local/bin/orcan-prompt-clean \
        /usr/local/bin/cursor-ttyd \
        /usr/local/bin/agent-launcher \
        /usr/local/bin/cursor-tmux-workspace-attach \
        /usr/local/bin/cursor-tmux-bootstrap-workspaces \
        /etc/tmux/scripts/*.sh \
    && chmod -R a+rX /opt/cursor-defaults \
    && find /opt/cursor-defaults -type f -exec chmod 0444 {} \; \
    && find /opt/cursor-defaults -type d -exec chmod 0555 {} \; \
    && chmod 0644 /etc/profile.d/orcan-path.sh \
    && chmod -R a+rX /etc/skel \
    && chmod -R a+rX /opt/orcan \
    && chmod 0644 /opt/orcan/gitconfig /opt/orcan/starship.toml \
    && chmod 0644 /etc/orcan/shell/aliases.sh

# ------------------------------------------------------------------------------
# User
# ------------------------------------------------------------------------------

RUN set -eux; \
    existing_user="$(getent passwd "${USER_UID}" | cut -d: -f1 || true)"; \
    existing_group="$(getent group "${USER_GID}" | cut -d: -f1 || true)"; \
    \
    if [ -z "${existing_group}" ]; then \
        groupadd --gid "${USER_GID}" "${USERNAME}"; \
        existing_group="${USERNAME}"; \
    fi; \
    \
    if [ -n "${existing_user}" ]; then \
        usermod \
            --login "${USERNAME}" \
            --home "/home/${USERNAME}" \
            --move-home \
            --shell /bin/zsh \
            --gid "${existing_group}" \
            "${existing_user}"; \
    else \
        useradd \
            --uid "${USER_UID}" \
            --gid "${existing_group}" \
            --create-home \
            --shell /bin/zsh \
            "${USERNAME}"; \
    fi; \
    \
    echo "${USERNAME} ALL=(ALL) NOPASSWD:ALL" \
        > "/etc/sudoers.d/${USERNAME}"; \
    chmod 0440 "/etc/sudoers.d/${USERNAME}"; \
    \
    docker_group="docker"; \
    if getent group docker >/dev/null; then \
        :; \
    elif getent group "${DOCKER_GID}" >/dev/null; then \
        docker_group="$(getent group "${DOCKER_GID}" | cut -d: -f1)"; \
    else \
        groupadd --gid "${DOCKER_GID}" docker; \
    fi; \
    usermod -aG "${docker_group}" "${USERNAME}"; \
    \
    mkdir -p \
        "/home/${USERNAME}/.cache" \
        "/home/${USERNAME}/.cache/npm" \
        "/home/${USERNAME}/.cache/pnpm" \
        "/home/${USERNAME}/.cache/cargo/bin" \
        "/home/${USERNAME}/.cache/go" \
        "/home/${USERNAME}/.cache/go-build" \
        "/home/${USERNAME}/.config" \
        "/home/${USERNAME}/.config/cursor" \
        "/home/${USERNAME}/.local/bin" \
        "/home/${USERNAME}/.local/share/orcan/history" \
        "/home/${USERNAME}/.bashrc.d" \
        "/home/${USERNAME}/.zshrc.d" \
        "/home/${USERNAME}/.cursor" \
        "/home/${USERNAME}/orcan"; \
    \
    # Install shell configs from skel (safe if useradd already copied them).
    cp -a /etc/skel/.bashrc.d/. "/home/${USERNAME}/.bashrc.d/"; \
    cp -a /etc/skel/.zshrc.d/. "/home/${USERNAME}/.zshrc.d/"; \
    cp -a /etc/skel/.zshrc "/home/${USERNAME}/.zshrc"; \
    cp -a /etc/skel/.tmux.conf "/home/${USERNAME}/.tmux.conf"; \
    cp -a /etc/skel/.vimrc "/home/${USERNAME}/.vimrc"; \
    ln -sfn /etc/tmux "/home/${USERNAME}/.config/tmux"; \
    mkdir -p "/home/${USERNAME}/.cache/tmux" "/home/${USERNAME}/.config"; \
    if [[ ! -e "/home/${USERNAME}/.config/starship.toml" ]]; then \
        cp -a /opt/orcan/starship.toml "/home/${USERNAME}/.config/starship.toml"; \
    fi; \
    if [[ ! -e "/home/${USERNAME}/.gitconfig" ]]; then \
        cp -a /opt/orcan/gitconfig "/home/${USERNAME}/.gitconfig"; \
    fi; \
    \
    if ! grep -q 'bashrc.d' "/home/${USERNAME}/.bashrc"; then \
        printf '\n# Container shell snippets\nfor f in "$HOME"/.bashrc.d/*.sh; do\n  [ -r "$f" ] && . "$f"\ndone\n' \
            >> "/home/${USERNAME}/.bashrc"; \
    fi; \
    \
    if ! grep -q 'orcan-path\|cursor-dev-path\|/usr/local/go/bin' "/home/${USERNAME}/.profile"; then \
        printf '\n# Toolchain PATH for login shells\n. /etc/profile.d/orcan-path.sh\n' \
            >> "/home/${USERNAME}/.profile"; \
    fi; \
    \
    chown -R "${USER_UID}:${USER_GID}" \
        "/home/${USERNAME}"

# ------------------------------------------------------------------------------
# Environment
# ------------------------------------------------------------------------------

ENV HOME=/home/${USERNAME}
ENV XDG_CACHE_HOME=/home/${USERNAME}/.cache
ENV npm_config_cache=/home/${USERNAME}/.cache/npm
ENV PNPM_HOME=/home/${USERNAME}/.cache/pnpm
ENV CARGO_HOME=/home/${USERNAME}/.cache/cargo
ENV RUSTUP_HOME=/usr/local/rustup
ENV GOPATH=/home/${USERNAME}/.cache/go
ENV GOCACHE=/home/${USERNAME}/.cache/go-build
ENV GOMODCACHE=/home/${USERNAME}/.cache/go/pkg/mod
ENV UV_CACHE_DIR=/home/${USERNAME}/.cache/uv
ENV RUFF_CACHE_DIR=/home/${USERNAME}/.cache/ruff
ENV MYPY_CACHE_DIR=/home/${USERNAME}/.cache/mypy
ENV PIP_CACHE_DIR=/home/${USERNAME}/.cache/pip
ENV PRE_COMMIT_HOME=/home/${USERNAME}/.cache/pre-commit
ENV HISTFILE=/home/${USERNAME}/.local/share/orcan/history/.zsh_history
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTEST_ADDOPTS="-p no:cacheprovider"
ENV CLAUDE_CONFIG_DIR=/home/${USERNAME}/.claude
# Prefer system ripgrep on PATH (faster than Claude's bundled wrapper).
ENV USE_BUILTIN_RIPGREP=0
ENV PATH="/home/${USERNAME}/.local/bin:/home/${USERNAME}/.cache/cargo/bin:/home/${USERNAME}/.cache/pnpm:/home/${USERNAME}/.cache/go/bin:/usr/local/go/bin:/usr/local/cargo/bin:${PATH}"

USER ${USERNAME}
WORKDIR /home/${USERNAME}

# ------------------------------------------------------------------------------
# AI CLIs — INSTALL_CLAUDE / INSTALL_CURSOR / INSTALL_CODEX (default: all → variant full)
# ------------------------------------------------------------------------------
# Image tags: orcan:latest + orcan:<VERSION> (all agents);
#             orcan:<VERSION>-claude / -cursor / -codex (local single-agent builds).
# Slim builds: orcan build --claude|--cursor|--codex (skip pull; do not publish).

ARG INSTALL_CURSOR=1
ARG INSTALL_CLAUDE=1
ARG INSTALL_CODEX=1
ARG ORCAN_VERSION=dev

RUN set -eux; \
    if [ "${INSTALL_CLAUDE}" = "1" ] || [ "${INSTALL_CLAUDE}" = "true" ]; then \
        for attempt in 1 2 3; do \
            if curl -fsSL https://claude.ai/install.sh | bash; then break; fi; \
            echo "Claude install attempt ${attempt} failed, retrying..." >&2; \
            sleep 10; \
        done; \
        claude --version; \
    else \
        printf 'Skipping Claude Code (INSTALL_CLAUDE=%s)\n' "${INSTALL_CLAUDE}" >&2; \
    fi
# Claude config lives under ~/.claude (bind: $ORCAN_DATA/claude).

RUN set -eux; \
    if [ "${INSTALL_CURSOR}" = "1" ] || [ "${INSTALL_CURSOR}" = "true" ]; then \
        for attempt in 1 2 3; do \
            if curl -fsSL https://cursor.com/install | bash; then break; fi; \
            echo "Cursor install attempt ${attempt} failed, retrying..." >&2; \
            sleep 10; \
        done; \
        agent --version; \
        rm -rf "${HOME}/.cursor"; \
        mkdir -p "${HOME}/.cursor"; \
    else \
        printf 'Skipping Cursor CLI (INSTALL_CURSOR=%s)\n' "${INSTALL_CURSOR}" >&2; \
    fi
# Empty ~/.cursor so the first volume mount stays writable; seeded at runtime.

RUN set -eux; \
    if [ "${INSTALL_CODEX}" = "1" ] || [ "${INSTALL_CODEX}" = "true" ]; then \
        for attempt in 1 2 3; do \
            if npm install -g --prefix "${HOME}/.local" @openai/codex; then break; fi; \
            echo "Codex install attempt ${attempt} failed, retrying..." >&2; \
            sleep 10; \
        done; \
        codex --version; \
    else \
        printf 'Skipping Codex CLI (INSTALL_CODEX=%s)\n' "${INSTALL_CODEX}" >&2; \
    fi
# Installed under ~/.local (not pnpm add -g — PNPM_HOME is bind-mounted at
# runtime from ORCAN_DATA/cache/pnpm, which would shadow a baked-in global
# with an empty host dir on first boot). ~/.local/bin is already on PATH
# and is not bind-mounted, same as the Claude/Cursor native installers.
# Codex config lives under ~/.codex (bind: $ORCAN_DATA/codex).

RUN set -eux; \
    cursor_on=0; claude_on=0; codex_on=0; \
    if [ "${INSTALL_CURSOR}" = "1" ] || [ "${INSTALL_CURSOR}" = "true" ]; then cursor_on=1; fi; \
    if [ "${INSTALL_CLAUDE}" = "1" ] || [ "${INSTALL_CLAUDE}" = "true" ]; then claude_on=1; fi; \
    if [ "${INSTALL_CODEX}" = "1" ] || [ "${INSTALL_CODEX}" = "true" ]; then codex_on=1; fi; \
    if [ "${cursor_on}" = "0" ] && [ "${claude_on}" = "0" ] && [ "${codex_on}" = "0" ]; then \
        echo "Error: at least one of INSTALL_CLAUDE / INSTALL_CURSOR / INSTALL_CODEX must be enabled" >&2; \
        exit 1; \
    fi; \
    if [ "${cursor_on}" = "1" ] && [ "${claude_on}" = "1" ] && [ "${codex_on}" = "1" ]; then \
        printf 'full' > /tmp/orcan-variant; \
    else \
        variant=""; \
        [ "${claude_on}" = "1" ] && variant="${variant}claude+"; \
        [ "${cursor_on}" = "1" ] && variant="${variant}cursor+"; \
        [ "${codex_on}" = "1" ] && variant="${variant}codex+"; \
        printf '%s' "${variant%+}" > /tmp/orcan-variant; \
    fi

USER root
ARG ORCAN_VERSION=dev
RUN install -d -m 0755 /etc/orcan \
    && mv /tmp/orcan-variant /etc/orcan/variant \
    && printf '%s\n' "${ORCAN_VERSION}" > /etc/orcan/version \
    && chmod 0644 /etc/orcan/variant /etc/orcan/version \
    && chown root:root /etc/orcan/variant /etc/orcan/version

LABEL org.opencontainers.image.title="Orcan" \
      org.opencontainers.image.description="Context orchestrator for Cursor CLI and Claude Code" \
      org.opencontainers.image.source="https://github.com/aKyther/orcan" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${ORCAN_VERSION}"

ENV ORCAN_VERSION="${ORCAN_VERSION}"

USER ${USERNAME}

ENTRYPOINT ["docker-entrypoint"]
CMD ["zsh"]
