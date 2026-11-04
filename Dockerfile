# syntax=docker/dockerfile:1.7

# ------------------------------------------------------------------------------
# Tool stages
# ------------------------------------------------------------------------------

ARG GO_IMAGE=golang:1.27-bookworm
ARG RUST_IMAGE=rust:1-bookworm

FROM node:22-bookworm-slim AS node-tools

# No network fetch here — final stage installs pnpm with a pinned version.

FROM ${GO_IMAGE} AS go-tools

FROM ${RUST_IMAGE} AS rust-tools

FROM ghcr.io/astral-sh/uv:latest AS uv-tools

# ------------------------------------------------------------------------------
# Final image
# ------------------------------------------------------------------------------

FROM debian:bookworm-slim AS core

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
        dnsutils \
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
        pkg-config \
        libayatana-appindicator3-dev \
        libdbus-1-dev \
        libglib2.0-dev \
        libgtk-3-dev \
        librsvg2-dev \
        libssl-dev \
        libwebkit2gtk-4.1-dev \
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
        redis-server \
        redis-tools \
        ripgrep \
        rsync \
        shellcheck \
        sshpass \
        sqlite3 \
        sudo \
        supervisor \
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
# Node.js + npm + pnpm + Corepack
# ------------------------------------------------------------------------------

ARG PNPM_VERSION=10.12.1
ARG NPM_MAJOR=10

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
    ln -sf ../lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack; \
    corepack enable yarn; \
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
    npm --version | grep -E "^${NPM_MAJOR}\\."; \
    corepack --version; \
    pnpm --version

# ------------------------------------------------------------------------------
# Go / Rust / uv
# ------------------------------------------------------------------------------

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

ARG YQ_VERSION=4.53.6

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "${arch}" in \
        amd64) yq_arch="amd64" ;; \
        arm64) yq_arch="arm64" ;; \
        *) echo "unsupported architecture for yq: ${arch}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/mikefarah/yq/releases/download/v${YQ_VERSION}/yq_linux_${yq_arch}" \
        -o /usr/local/bin/yq; \
    chmod 0755 /usr/local/bin/yq; \
    yq --version

# ------------------------------------------------------------------------------
# gh (GitHub CLI) + glab (GitLab CLI) + ast-grep (structural search) — agents use these on PATH
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
        *) echo "unsupported architecture for gh/glab/ast-grep: ${arch}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${gh_arch}.tar.gz" \
        | tar -xz --strip-components=1 -C /usr/local \
            "gh_${GH_VERSION}_linux_${gh_arch}/bin/gh"; \
    chmod 0755 /usr/local/bin/gh; \
    gh --version; \
    tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT; \
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

# GitLab CLI — pinned release and architecture-specific SHA-256 checksums.
ARG GLAB_VERSION=1.122.0
ARG GLAB_SHA256_AMD64=242326668011a110ea6dcbe865cfbf3ab763f9909851c90ef0da23ab1f2f3808
ARG GLAB_SHA256_ARM64=78910c21b6b517c0936e413df96e59f942558a3a4e4109370a452761f7d0f253

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "${arch}" in \
        amd64) glab_sha256="${GLAB_SHA256_AMD64}" ;; \
        arm64) glab_sha256="${GLAB_SHA256_ARM64}" ;; \
        *) echo "unsupported architecture for glab: ${arch}" >&2; exit 1 ;; \
    esac; \
    tmp="$(mktemp -d)"; \
    curl -fsSL "https://gitlab.com/gitlab-org/cli/-/releases/v${GLAB_VERSION}/downloads/glab_${GLAB_VERSION}_linux_${arch}.tar.gz" \
        -o "${tmp}/glab.tar.gz"; \
    printf '%s  %s\n' "${glab_sha256}" "${tmp}/glab.tar.gz" | sha256sum -c -; \
    tar -xzf "${tmp}/glab.tar.gz" -C "${tmp}" bin/glab; \
    install -m 0755 "${tmp}/bin/glab" /usr/local/bin/glab; \
    rm -rf "${tmp}"; \
    glab --version

# ------------------------------------------------------------------------------
# Starship + delta + lazygit (shell / git UX)
# ------------------------------------------------------------------------------

ARG STARSHIP_VERSION=1.22.1
ARG DELTA_VERSION=0.18.2
ARG LAZYGIT_VERSION=0.64.1

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
# bottom + dust + procs (modern top / du / ps — same "faster replacement"
# convention as rg/fd/eza/bat/delta/difft above)
# ------------------------------------------------------------------------------

ARG BOTTOM_VERSION=0.10.2
ARG DUST_VERSION=1.1.2
ARG PROCS_VERSION=0.14.9

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "${arch}" in \
        amd64) \
            bottom_arch="x86_64-unknown-linux-gnu"; \
            dust_arch="x86_64-unknown-linux-gnu"; \
            procs_arch="x86_64-linux"; \
            ;; \
        arm64) \
            bottom_arch="aarch64-unknown-linux-gnu"; \
            dust_arch="aarch64-unknown-linux-gnu"; \
            procs_arch="aarch64-linux"; \
            ;; \
        *) echo "unsupported architecture for bottom/dust/procs: ${arch}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/ClementTsang/bottom/releases/download/${BOTTOM_VERSION}/bottom_${bottom_arch}.tar.gz" \
        | tar -xz -C /usr/local/bin btm; \
    chmod 0755 /usr/local/bin/btm; \
    btm --version; \
    curl -fsSL "https://github.com/bootandy/dust/releases/download/v${DUST_VERSION}/dust-v${DUST_VERSION}-${dust_arch}.tar.gz" \
        | tar -xz --strip-components=1 -C /usr/local/bin \
            "dust-v${DUST_VERSION}-${dust_arch}/dust"; \
    chmod 0755 /usr/local/bin/dust; \
    dust --version; \
    tmp="$(mktemp -d)"; \
    curl -fsSL "https://github.com/dalance/procs/releases/download/v${PROCS_VERSION}/procs-v${PROCS_VERSION}-${procs_arch}.zip" \
        -o "${tmp}/procs.zip"; \
    unzip -q "${tmp}/procs.zip" -d /usr/local/bin; \
    chmod 0755 /usr/local/bin/procs; \
    rm -rf "${tmp}"; \
    procs --version

# Independent SDK builders: only this component's version affects its stage.
FROM core AS jvm-installer
COPY --chmod=0755 docker/installers/install-jvm.sh /usr/local/libexec/orcan-install-jvm

FROM jvm-installer AS jdk-tools
ARG JAVA_VERSION=21
ARG INSTALL_JAVA=1
RUN /usr/local/libexec/orcan-install-jvm jdk "${INSTALL_JAVA}" "${JAVA_VERSION}" /opt/java

FROM jvm-installer AS gradle-tools
ARG GRADLE_VERSION=8.11
ARG INSTALL_GRADLE=1
RUN /usr/local/libexec/orcan-install-jvm gradle "${INSTALL_GRADLE}" "${GRADLE_VERSION}" /opt/gradle

FROM jvm-installer AS maven-tools
ARG MAVEN_VERSION=3.9.9
ARG INSTALL_MAVEN=1
RUN /usr/local/libexec/orcan-install-jvm maven "${INSTALL_MAVEN}" "${MAVEN_VERSION}" /opt/maven

FROM jvm-installer AS kotlin-tools
ARG KOTLIN_VERSION=2.1.0
ARG INSTALL_KOTLIN=1
RUN /usr/local/libexec/orcan-install-jvm kotlin "${INSTALL_KOTLIN}" "${KOTLIN_VERSION}" /opt/kotlinc

FROM jvm-installer AS scala-tools
ARG SCALA_VERSION=3.5.2
ARG INSTALL_SCALA=1
RUN /usr/local/libexec/orcan-install-jvm scala "${INSTALL_SCALA}" "${SCALA_VERSION}" /opt/scala3

FROM jvm-installer AS sbt-tools
ARG SBT_VERSION=1.10.5
ARG INSTALL_SBT=1
RUN /usr/local/libexec/orcan-install-jvm sbt "${INSTALL_SBT}" "${SBT_VERSION}" /opt/sbt

# Dependency wheels are isolated from project source and optional SDK choices.
FROM core AS cockpit-deps
COPY cockpit/pyproject.toml cockpit/uv.lock /opt/orcan-cockpit-src/
RUN --mount=type=cache,id=orcan-cockpit-wheels,target=/root/.cache/uv,sharing=locked \
    cd /opt/orcan-cockpit-src \
    && UV_PROJECT_ENVIRONMENT=/opt/orcan-cockpit/venv uv sync --frozen --no-install-project --python /usr/bin/python3 \
    && chmod -R a+rX /opt/orcan-cockpit/venv

FROM core AS executor-deps
COPY executor/pyproject.toml executor/uv.lock /opt/orcan-executor-src/
RUN --mount=type=cache,id=orcan-executor-wheels,target=/root/.cache/uv,sharing=locked \
    cd /opt/orcan-executor-src \
    && UV_PYTHON_INSTALL_DIR=/opt/python UV_PROJECT_ENVIRONMENT=/opt/orcan-executor/venv uv sync --frozen --no-dev --no-install-project --python 3.12 \
    && chmod -R a+rX /opt/orcan-executor/venv /opt/python

# Public image: core layers are inherited, never copied into a giant new layer.
FROM jdk-tools AS runtime
ARG USERNAME=developer
ARG USER_UID=1000
ARG USER_GID=1000
ARG DOCKER_GID=999
# Bind-mounted tool stages do not add their bytes to disabled runtime layers.
ARG INSTALL_GO=1
ARG INSTALL_RUST=1
RUN --mount=from=go-tools,source=/,target=/tmp/orcan-go,ro \
    if [ "${INSTALL_GO}" = "1" ]; then mkdir -p /usr/local/go; cp -a /tmp/orcan-go/usr/local/go/. /usr/local/go/; fi
RUN --mount=from=rust-tools,source=/,target=/tmp/orcan-rust,ro \
    if [ "${INSTALL_RUST}" = "1" ]; then \
        mkdir -p /usr/local/cargo /usr/local/rustup; \
        cp -a /tmp/orcan-rust/usr/local/cargo/. /usr/local/cargo/; cp -a /tmp/orcan-rust/usr/local/rustup/. /usr/local/rustup/; \
    fi
RUN mkdir -p /etc/orcan && printf '{"tools":{"go":%s,"rust":%s}}\n' "${INSTALL_GO}" "${INSTALL_RUST}" > /etc/orcan/tools.json
# ------------------------------------------------------------------------------
# Additional Python runtime
# ------------------------------------------------------------------------------

# Project runtimes are separate from the system Python and service venvs.
ARG ORCAN_PYTHON_VERSIONS="3.13"
RUN set -eux; \
    first=1; \
    for version in ${ORCAN_PYTHON_VERSIONS}; do \
        case "$version" in 3.11|3.12|3.13) ;; *) exit 1 ;; esac; \
        UV_NO_CACHE=1 uv python install --install-dir /opt/project-python "$version"; \
        executable="$(find /opt/project-python -type f -path "*/bin/python${version}" -print -quit)"; \
        test -x "$executable"; \
        ln -sf "$executable" "/usr/local/bin/python${version}"; \
        if [ "$first" = 1 ]; then ln -sf "$executable" /usr/local/bin/python3; ln -sf "$executable" /usr/local/bin/python; first=0; fi; \
    done

# ------------------------------------------------------------------------------
# JVM: Java (Temurin) + Gradle + Maven + Kotlin + Scala + sbt
# ------------------------------------------------------------------------------
# Kotlin/Scala/Gradle/Maven/sbt are pure-JVM archives (no per-arch build) —
# only the JDK itself needs the amd64/arm64 split below. Adoptium's
# "latest GA build for this major version" endpoint is used for Java instead
# of a full build string (e.g. 21.0.12+7) so this ARG only has to track a
# major version, not a moving exact-build filename.

ARG INSTALL_GRADLE=1
COPY --link --from=gradle-tools /opt/gradle/ /opt/gradle/
ARG INSTALL_MAVEN=1
COPY --link --from=maven-tools /opt/maven/ /opt/maven/
ARG INSTALL_KOTLIN=1
COPY --link --from=kotlin-tools /opt/kotlinc/ /opt/kotlinc/
ARG INSTALL_SCALA=1
COPY --link --from=scala-tools /opt/scala3/ /opt/scala3/
ARG INSTALL_SBT=1
COPY --link --from=sbt-tools /opt/sbt/ /opt/sbt/

# ------------------------------------------------------------------------------
# Container filesystem (scripts, defaults, shell configs)
# ------------------------------------------------------------------------------

COPY docker/rootfs/ /
COPY plugins/ /opt/orcan/plugins/

RUN set -eux; \
    ttyd --writable --interface 127.0.0.1 --port 17778 sh >/tmp/ttyd-index-build.log 2>&1 & \
    ttyd_pid="$!"; \
    trap 'kill "${ttyd_pid}" 2>/dev/null || true' EXIT; \
    for attempt in $(seq 1 50); do \
        if curl -fsS http://127.0.0.1:17778/ -o /tmp/ttyd-index.html; then break; fi; \
        sleep 0.1; \
    done; \
    test -s /tmp/ttyd-index.html; \
    python3 - <<'PY'
from pathlib import Path

index = Path("/tmp/ttyd-index.html").read_text(encoding="utf-8")
touch = Path("/opt/orcan/ttyd-touch.js").read_text(encoding="utf-8")
if 'name="viewport"' not in index:
    head = "</head>"
    if head not in index:
        raise SystemExit("ttyd index has no </head> viewport injection point")
    index = index.replace(
        head,
        '<meta name="viewport" content="width=device-width, initial-scale=1, '
        'viewport-fit=cover, interactive-widget=resizes-content">'
        + head,
        1,
    )
needle = "</body>"
if needle not in index:
    raise SystemExit("ttyd index has no </body> injection point")
Path("/opt/orcan/ttyd-index.html").write_text(
    index.replace(needle, f"<script>{touch}</script>{needle}", 1),
    encoding="utf-8",
)
PY

RUN chmod 0755 \
        /usr/local/bin/ssh \
        /usr/local/bin/docker-entrypoint \
        /usr/local/bin/init-cursor-home \
        /usr/local/bin/init-claude-home \
        /usr/local/bin/init-ai-statusline \
        /usr/local/bin/orcan-ai-statusline \
        /usr/local/bin/init-workspace \
        /usr/local/bin/cursor-init-project \
        /usr/local/bin/orcan-init-projects \
        /usr/local/bin/orcan-init-project \
        /usr/local/bin/orcan-agent-enabled \
        /usr/local/bin/orcan-session-brief \
        /usr/local/bin/orcan-compact \
        /usr/local/bin/orcan-actions \
        /usr/local/bin/orcan-workspaces \
        /usr/local/bin/orcan-context-status \
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


COPY --link --from=cockpit-deps /opt/orcan-cockpit/venv /opt/orcan-cockpit/venv
COPY --link --from=executor-deps /opt/orcan-executor/venv /opt/orcan-executor/venv
COPY --link --from=executor-deps /opt/python /opt/python
COPY cockpit/ /opt/orcan-cockpit-src/
COPY executor/ /opt/orcan-executor-src/
RUN cd /opt/orcan-cockpit-src \
    && UV_NO_CACHE=1 UV_PROJECT_ENVIRONMENT=/opt/orcan-cockpit/venv uv sync --frozen --python /usr/bin/python3 \
    && cd /opt/orcan-executor-src \
    && UV_PYTHON_INSTALL_DIR=/opt/python UV_NO_CACHE=1 UV_PROJECT_ENVIRONMENT=/opt/orcan-executor/venv uv sync --frozen --no-dev --python 3.12 \
    && chmod -R a+rX /opt/orcan-cockpit-src /opt/orcan-executor-src \
    && /opt/orcan-cockpit/venv/bin/python3 -c 'import orcan_cockpit, textual, pyte, libtmux, watchfiles' \
    && test -x /opt/orcan-cockpit/venv/bin/orcan-cockpit

# Offline action classification has its own Python environment. Other context
# helpers remain stdlib-only. Ollama is optional and is not installed here.
ARG INSTALL_ACTIONS_ML=0
COPY requirements-actions.txt /opt/orcan/requirements-actions.txt
RUN if [ "${INSTALL_ACTIONS_ML}" = "1" ]; then \
        uv venv --python /usr/bin/python3 /opt/orcan-actions/venv \
        && uv pip install --no-cache --python /opt/orcan-actions/venv/bin/python \
            -r /opt/orcan/requirements-actions.txt \
        && /opt/orcan-actions/venv/bin/python -c 'import sklearn, scipy, numpy' \
        && chmod -R a+rX /opt/orcan-actions; \
    fi

RUN uv cache clean

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
ENV JAVA_HOME=/opt/java
ENV GRADLE_USER_HOME=/home/${USERNAME}/.cache/gradle
# Maven's local repo (~/.m2) and sbt/Coursier's cache are left at their own
# tool defaults (Coursier already respects XDG_CACHE_HOME, i.e.
# ~/.cache/coursier, on Linux) rather than redirected — .m2 in particular is
# such an established convention that IDEs/other tooling expect it there.
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
ENV PATH="/home/${USERNAME}/.local/bin:/home/${USERNAME}/.cache/cargo/bin:/home/${USERNAME}/.cache/pnpm:/home/${USERNAME}/.cache/go/bin:/usr/local/go/bin:/usr/local/cargo/bin:/opt/java/bin:/opt/gradle/bin:/opt/maven/bin:/opt/kotlinc/bin:/opt/scala3/bin:/opt/sbt/bin:${PATH}"

RUN set -eux; \
    temporary="$(mktemp -d)"; trap 'rm -rf "$temporary"' EXIT; \
    export GRADLE_USER_HOME="$temporary/gradle" XDG_CACHE_HOME="$temporary/cache"; \
    if [ "${INSTALL_JAVA}" = 1 ]; then java -version; fi; \
    if [ "${INSTALL_GRADLE}" = 1 ]; then gradle --version; fi; \
    if [ "${INSTALL_MAVEN}" = 1 ]; then mvn --version; fi; \
    if [ "${INSTALL_KOTLIN}" = 1 ]; then kotlinc -version; fi; \
    if [ "${INSTALL_SCALA}" = 1 ]; then scala -version; fi; \
    if [ "${INSTALL_SBT}" = 1 ]; then sbt --script-version; fi

USER ${USERNAME}
WORKDIR /home/${USERNAME}

# ------------------------------------------------------------------------------
# AI CLIs — selected explicitly by `orcan build --agent …`.
# ------------------------------------------------------------------------------
# Every image is tagged orcan:latest + orcan:<VERSION>. The explicit agent
# selection is recorded in /etc/orcan/agents.json rather than the tag.

ARG ORCAN_BUILD_PROFILE_JSON=
ARG INSTALL_CURSOR=1
ARG INSTALL_CLAUDE=1
ARG INSTALL_CODEX=1
ARG INSTALL_GEMINI=1
ARG INSTALL_COPILOT=1
ARG ORCAN_VERSION=dev

RUN set -eux; \
    for name in claude cursor codex gemini copilot; do \
        case "$name" in \
            claude) selected="${INSTALL_CLAUDE}" ;; cursor) selected="${INSTALL_CURSOR}" ;; \
            codex) selected="${INSTALL_CODEX}" ;; gemini) selected="${INSTALL_GEMINI}" ;; copilot) selected="${INSTALL_COPILOT}" ;; \
        esac; \
        if [ "$selected" = "1" ] || [ "$selected" = "true" ]; then \
            /opt/orcan-executor/venv/bin/python /usr/local/lib/orcan/install_agent.py "$name"; \
        fi; \
    done; \
    npm cache clean --force

RUN set -eux; \
    cursor_on=0; claude_on=0; codex_on=0; gemini_on=0; copilot_on=0; \
    if [ "${INSTALL_CURSOR}" = "1" ] || [ "${INSTALL_CURSOR}" = "true" ]; then cursor_on=1; fi; \
    if [ "${INSTALL_CLAUDE}" = "1" ] || [ "${INSTALL_CLAUDE}" = "true" ]; then claude_on=1; fi; \
    if [ "${INSTALL_CODEX}" = "1" ] || [ "${INSTALL_CODEX}" = "true" ]; then codex_on=1; fi; \
    if [ "${INSTALL_GEMINI}" = "1" ] || [ "${INSTALL_GEMINI}" = "true" ]; then gemini_on=1; fi; \
    if [ "${INSTALL_COPILOT}" = "1" ] || [ "${INSTALL_COPILOT}" = "true" ]; then copilot_on=1; fi; \
    if [ "${cursor_on}${claude_on}${codex_on}${gemini_on}${copilot_on}" = "00000" ]; then \
        echo "Error: at least one agent must be enabled" >&2; \
        exit 1; \
    fi; \
    printf '{"agents":{"cursor":%s,"claude":%s,"codex":%s,"gemini":%s,"copilot":%s}}\n' "${cursor_on}" "${claude_on}" "${codex_on}" "${gemini_on}" "${copilot_on}" > /tmp/orcan-agents.json

USER root
ARG ORCAN_VERSION=dev
RUN install -d -m 0755 /etc/orcan \
    && mv /tmp/orcan-agents.json /etc/orcan/agents.json \
    && printf '%s\n' "${ORCAN_VERSION}" > /etc/orcan/version \
    && profile_json="${ORCAN_BUILD_PROFILE_JSON:-}" \
    && if [ -z "$profile_json" ]; then profile_json='{}'; fi \
    && printf '%s\n' "$profile_json" > /etc/orcan/build-profile.json \
    && chmod 0644 /etc/orcan/agents.json /etc/orcan/version \
    && chown root:root /etc/orcan/agents.json /etc/orcan/version

LABEL io.orcan.identity.version="1" \
      io.orcan.agent.cursor="${INSTALL_CURSOR}" \
      io.orcan.agent.claude="${INSTALL_CLAUDE}" \
      io.orcan.agent.codex="${INSTALL_CODEX}" \
      io.orcan.agent.gemini="${INSTALL_GEMINI}" \
      io.orcan.agent.copilot="${INSTALL_COPILOT}" \
      org.opencontainers.image.title="Orcan" \
      org.opencontainers.image.description="Context orchestrator for Cursor CLI and Claude Code" \
      org.opencontainers.image.source="https://github.com/aKyther/orcan" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${ORCAN_VERSION}"

ENV ORCAN_VERSION="${ORCAN_VERSION}"

USER ${USERNAME}

ENTRYPOINT ["docker-entrypoint"]
CMD ["zsh"]
