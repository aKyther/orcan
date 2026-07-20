# syntax=docker/dockerfile:1.7

# ------------------------------------------------------------------------------
# Tool stages
# ------------------------------------------------------------------------------

FROM node:22-bookworm-slim AS node-tools

RUN corepack enable \
    && corepack prepare pnpm@latest --activate

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
    && apt-get install -y --no-install-recommends \
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
        jq \
        less \
        make \
        nano \
        openssh-client \
        openssh-server \
        parallel \
        postgresql-client \
        python3 \
        python3-pip \
        python3-venv \
        redis-tools \
        ripgrep \
        shellcheck \
        sudo \
        tmux \
        unzip \
        vim \
        wget \
        zip \
        zstd \
    && ln -sf /usr/bin/fdfind /usr/local/bin/fd \
    && ln -sf /usr/bin/batcat /usr/local/bin/bat \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------------------------
# Node.js + npm + pnpm
# ------------------------------------------------------------------------------

COPY --from=node-tools /usr/local/bin/node /usr/local/bin/node
COPY --from=node-tools /usr/local/lib/node_modules /usr/local/lib/node_modules

RUN ln -sf node /usr/local/bin/nodejs \
    && ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && ln -sf ../lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack \
    && corepack enable \
    && corepack prepare pnpm@latest --activate \
    && node --version \
    && npm --version \
    && pnpm --version

# ------------------------------------------------------------------------------
# Go / Rust / uv
# ------------------------------------------------------------------------------

COPY --from=go-tools /usr/local/go /usr/local/go
COPY --from=rust-tools /usr/local/cargo /usr/local/cargo
COPY --from=rust-tools /usr/local/rustup /usr/local/rustup
COPY --from=uv-tools /uv /usr/local/bin/uv
COPY --from=uv-tools /uvx /usr/local/bin/uvx

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
# Container filesystem (scripts, defaults, shell configs)
# ------------------------------------------------------------------------------

COPY docker/rootfs/ /

RUN chmod 0755 \
        /usr/local/bin/docker-entrypoint \
        /usr/local/bin/init-cursor-home \
        /usr/local/bin/cursor-init-project \
        /usr/local/bin/cursor-sshd \
    && chmod -R a+rX /opt/cursor-defaults \
    && find /opt/cursor-defaults -type f -exec chmod 0444 {} \; \
    && find /opt/cursor-defaults -type d -exec chmod 0555 {} \; \
    && chmod 0644 /etc/profile.d/cursor-dev-path.sh \
    && chmod -R a+rX /etc/skel

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
            --shell /bin/bash \
            --gid "${existing_group}" \
            "${existing_user}"; \
    else \
        useradd \
            --uid "${USER_UID}" \
            --gid "${existing_group}" \
            --create-home \
            --shell /bin/bash \
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
        /command-history \
        "/home/${USERNAME}/.cache" \
        "/home/${USERNAME}/.config" \
        "/home/${USERNAME}/.config/cursor" \
        "/home/${USERNAME}/.local/bin" \
        "/home/${USERNAME}/.local/share/pnpm" \
        "/home/${USERNAME}/.cargo" \
        "/home/${USERNAME}/go" \
        "/home/${USERNAME}/.bashrc.d" \
        "/home/${USERNAME}/.cursor"; \
    \
    # Install shell configs from skel (safe if useradd already copied them).
    cp -a /etc/skel/.bashrc.d/. "/home/${USERNAME}/.bashrc.d/"; \
    cp -a /etc/skel/.tmux.conf "/home/${USERNAME}/.tmux.conf"; \
    cp -a /etc/skel/.vimrc "/home/${USERNAME}/.vimrc"; \
    \
    if ! grep -q 'bashrc.d' "/home/${USERNAME}/.bashrc"; then \
        printf '\n# Container shell snippets\nfor f in "$HOME"/.bashrc.d/*.sh; do\n  [ -r "$f" ] && . "$f"\ndone\n' \
            >> "/home/${USERNAME}/.bashrc"; \
    fi; \
    \
    if ! grep -q 'cursor-dev-path\|/usr/local/go/bin' "/home/${USERNAME}/.profile"; then \
        printf '\n# Toolchain PATH for login shells\n. /etc/profile.d/cursor-dev-path.sh\n' \
            >> "/home/${USERNAME}/.profile"; \
    fi; \
    \
    chown -R "${USER_UID}:${USER_GID}" \
        /command-history \
        "/home/${USERNAME}"

# ------------------------------------------------------------------------------
# Environment
# ------------------------------------------------------------------------------

ENV HOME=/home/${USERNAME}
ENV PNPM_HOME=/home/${USERNAME}/.local/share/pnpm
ENV CARGO_HOME=/home/${USERNAME}/.cargo
ENV RUSTUP_HOME=/usr/local/rustup
ENV GOPATH=/home/${USERNAME}/go
ENV GOCACHE=/home/${USERNAME}/.cache/go-build
ENV GOMODCACHE=/home/${USERNAME}/go/pkg/mod
ENV UV_CACHE_DIR=/home/${USERNAME}/.cache/uv
ENV PATH="/home/${USERNAME}/.local/bin:/home/${USERNAME}/.cargo/bin:/home/${USERNAME}/.local/share/pnpm:/home/${USERNAME}/go/bin:/usr/local/go/bin:/usr/local/cargo/bin:${PATH}"

USER ${USERNAME}
WORKDIR /home/${USERNAME}

# ------------------------------------------------------------------------------
# Cursor CLI
# ------------------------------------------------------------------------------

RUN curl -fsSL https://cursor.com/install | bash \
    && agent --version \
    && rm -rf "${HOME}/.cursor" \
    && mkdir -p "${HOME}/.cursor"
# Empty developer-owned ~/.cursor so the first named-volume mount stays writable.
# Runtime seeding comes from /opt/cursor-defaults via init-cursor-home.

ENTRYPOINT ["docker-entrypoint"]
CMD ["bash"]
