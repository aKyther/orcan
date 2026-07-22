# Docker

This page explains the image, Compose files, volumes, and runtime user.

## Why Docker is used

Docker keeps the toolchain inside an image. Your host package manager stays clean. Every machine that builds this image gets the same tools.

## Repository files vs container files

| Repository path | Container path | Purpose |
| --- | --- | --- |
| `docker/rootfs/opt/cursor-defaults` | `/opt/cursor-defaults` | Image-provided Cursor defaults |
| `docker/rootfs/usr/local/bin/docker-entrypoint` | `/usr/local/bin/docker-entrypoint` | Container startup |
| `docker/rootfs/usr/local/bin/init-cursor-home` | `/usr/local/bin/init-cursor-home` | User config initialization |
| `docker/rootfs/usr/local/bin/cursor-init-project` | `/usr/local/bin/cursor-init-project` | Project template initialization |
| `docker/rootfs/usr/local/bin/cursor-ttyd` | `/usr/local/bin/cursor-ttyd` | Browser terminal (ttyd + tmux) |
| `docker/rootfs/etc/skel/.tmux.conf` | `/home/developer/.tmux.conf` | TMUX config |
| `docker/rootfs/etc/skel/.vimrc` | `/home/developer/.vimrc` | Vim config |
| `docker/rootfs/etc/skel/.bashrc.d/` | `/home/developer/.bashrc.d/` | Interactive shell setup |
| `docker/rootfs/etc/profile.d/cind-path.sh` | `/etc/profile.d/cind-path.sh` | Toolchain PATH (login shells) |
| `scripts/repository/` | *(not in image)* | Host-only helpers |

## Image filesystem (`docker/rootfs/`)

Files under `docker/rootfs/` are copied into the container image.
Their paths match the final container layout.

```text
docker/rootfs/
├── etc/
│   ├── cind/shell/aliases.sh
│   ├── profile.d/cind-path.sh
│   └── skel/
│       ├── .bashrc.d/50-cind-shell.sh
│       ├── .bashrc.d/60-cind-aliases.sh
│       ├── .tmux.conf
│       └── .vimrc
├── opt/
│   └── cursor-defaults/     → /opt/cursor-defaults
└── usr/
    └── local/
        └── bin/
            ├── docker-entrypoint
            ├── init-cursor-home
            ├── cursor-init-project
            └── cursor-ttyd
```

### Rules for container files

* Edit container files under `docker/rootfs/`, not in the repository root.
* Do not mix these assets with this repository's own `.cursor/` rules.
* `/opt/cursor-defaults` is immutable product config for the container user.
* Runtime writable state lives in `${HOME}/.cursor` (host: `$CIND_DATA/cursor`).

The Dockerfile copies this tree with `COPY docker/rootfs/ /`, then sets permissions on binaries and `/opt/cursor-defaults`.

## Dockerfile

The image is multi-stage:

| Stage | Source | Purpose |
| --- | --- | --- |
| `node-tools` | `node:22-bookworm-slim` | Node, npm, pnpm |
| `go-tools` | `golang:1.24-bookworm` | Go toolchain |
| `rust-tools` | `rust:1-bookworm` | Rustup / Cargo |
| `uv-tools` | `ghcr.io/astral-sh/uv:latest` | `uv` / `uvx` |
| final | `debian:bookworm-slim` | Runtime image |

### Python toolchain (agents + status bar)

Always in the image (no extra pip packages required for cind scripts):

| Tool | Notes |
| --- | --- |
| `python` / `python3` | Debian Bookworm (`python-is-python3`) |
| `pip3` / `python3-venv` / `python3-dev` | System installs and building wheels |
| `uv` / `uvx` | Preferred for project deps (`uv add`, `uv run`) |

`cind-ai-statusline` and tmux AI usage use **stdlib only** (`json`, `pathlib`, …). For project libraries, prefer `uv` in the workspace rather than `pip install` into the system Python.

Build flow:

1. Install packages and copy toolchains.
2. `COPY docker/rootfs/ /` (scripts, defaults, shell configs).
3. Create the non-root user and install skel configs.
4. Install Cursor CLI and ttyd as that user.
5. Set `ENTRYPOINT` / `CMD`.

There is **no SSH server** and no `openssh-client` in the image. Use Git over HTTPS.
Shell access is **browser-only**: ttyd → workspace picker → tmux (see [Security — Tailscale](security.md#remote-access-tailscale)).

!!! note

    The runtime user is non-root. `sudo` is available inside the container for package installs during a session.

## Compose files

### `docker-compose.yml` (base)

Service name: **`cind`**, image: **`cind:latest`**.

Provides:

* project bind mounts from `cind.config.json` (path parity + workspace roots)
* host binds under `CIND_DATA` (`~/.config/cind`) for Cursor/Claude state and caches
* resource limits and a `/tmp` tmpfs

Does **not** mount the Docker socket or host `~/.ssh`.

### `docker-compose.docker.yml` (overlay)

Adds:

* `/var/run/docker.sock`
* `group_add: DOCKER_GID`

### `docker-compose.ttyd.yml` (overlay)

Used by both `make terminal` and `make terminal-docker`. Adds:

* `command: cursor-ttyd` (browser terminal — no SSH)
* publishes `${TTYD_HOST_PORT:-7681}:7681`
* sets `TTYD_PORT`, `TTYD_FONT_SIZE`, workspace env vars
* `restart: unless-stopped`

Remote access: use **Tailscale** (or localhost). Open `http://<tailscale-ip>:7681`.

```bash
make terminal
```

Open `http://localhost:7681` in your browser (or run `make terminal` to print the URL).

!!! warning

    ttyd has no built-in authentication. Use only on localhost or a private network (Tailscale).
    Do not expose port `7681` to the public Internet without auth and TLS.

## Layout

```text
Host ~/.config/cind/                 Container
────────────────────────────────     ─────────────────────────────────
cursor/           ───────────────►   /home/developer/.cursor
cursor-app/       ───────────────►   /home/developer/.config/cursor
claude/           ───────────────►   /home/developer/.claude
cache/            ───────────────►   /home/developer/.cache
npm/              ───────────────►   /home/developer/.npm
pnpm/             ───────────────►   /home/developer/.local/share/pnpm
cargo/            ───────────────►   /home/developer/.cargo
go/               ───────────────►   /home/developer/go
bash-history/     ───────────────►   /command-history
```

Plus path-parity project mounts and `/opt/cursor-defaults` from the image.

## Host data (`CIND_DATA`)

Always on — same idea as poetry (`~/.config/pypoetry`) or pip: product state lives under the user’s config home.

Default path: **`$HOME/.config/cind`**.

`make env` (and first `make setup`):

1. Writes absolute `CIND_DATA=…` into `.env` if missing/empty
2. Creates the subdirectory tree (`cursor`, `claude`, caches, …)
3. Sets ownership to `USER_UID`/`USER_GID`

Override only when you need another location:

```dotenv
CIND_DATA=/custom/path/cind
```

| Host path | Container path | Why |
| --- | --- | --- |
| `$CIND_DATA/cursor` | `/home/developer/.cursor` | Cursor CLI config, chats, rules, skills |
| `$CIND_DATA/cursor-app` | `/home/developer/.config/cursor` | Cursor login (`auth.json`) |
| `$CIND_DATA/claude` | `/home/developer/.claude` | Claude Code login and state |
| `$CIND_DATA/cache` | `/home/developer/.cache` | General caches |
| `$CIND_DATA/npm` | `/home/developer/.npm` | npm cache |
| `$CIND_DATA/pnpm` | `/home/developer/.local/share/pnpm` | pnpm store/home |
| `$CIND_DATA/cargo` | `/home/developer/.cargo` | Cargo registry and binaries |
| `$CIND_DATA/go` | `/home/developer/go` | GOPATH modules and bins |
| `$CIND_DATA/bash-history` | `/command-history` | Shared bash history file |

No Docker **named volumes**. Data survives `make down` / `make clean`. Reset with `make clean-data`.

## User and permissions

Build args:

* `USERNAME` (default `developer`)
* `USER_UID`
* `USER_GID`
* `DOCKER_GID` (default `999`) — GID of the `docker` group; `developer` is added to this group at build time

Matching host UID/GID prevents root-owned files in your project tree.

For host Docker socket access, use `make env` (sets `DOCKER_GID` from `/var/run/docker.sock`) and a `*-docker` target. The Docker overlay also adds `group_add: DOCKER_GID` at runtime so socket access works even if the host GID changed since the last build.

## TMUX and Vim

`cursor-ttyd` starts a persistent TMUX session when you open the browser terminal:

* session name: `workspace` (`TMUX_SESSION_NAME`)
* working directory: `${PROJECT_DIR}`

Config sources:

| Repo file | Container path |
| --- | --- |
| `docker/rootfs/etc/skel/.tmux.conf` | `/home/developer/.tmux.conf` |
| `docker/rootfs/etc/skel/.vimrc` | `/home/developer/.vimrc` |

Interactive shells inside TMUX source `~/.bashrc.d/50-cind-shell.sh` (PATH, `cd` to workspace) and `60-cind-aliases.sh` (aliases from `/etc/cind/shell/aliases.sh`).

## Cursor defaults on host data

`$CIND_DATA/cursor` mounts at `/home/developer/.cursor`.

Defaults live in `/opt/cursor-defaults` and are copied in at startup when missing.
See [Cursor](cursor.md).

## Environment variables

| Variable | Role |
| --- | --- |
| `PROJECT_DIR` | Absolute host project path (same path inside the container) |
| `CIND_DATA` | Host data root (default `$HOME/.config/cind`) |
| `USER_UID` / `USER_GID` | Container user identity |
| `DOCKER_GID` | Socket group for `*-docker` targets |
| `CPUS` / `MEMORY` / `SHM_SIZE` / `TMPFS_SIZE` | Resource limits |
| `TTYD_PORT` | Container port for ttyd (default `7681`) |
| `TTYD_HOST_PORT` | Host port published for the browser terminal (default `7681`) |
| `TMUX_SESSION_NAME` | TMUX session name in the browser terminal (default `workspace`) |
| `IMAGE_REGISTRY` | Registry host for publish/pull (default `registry.gitlab.com`) |
| `IMAGE_REPOSITORY` | Path under registry, e.g. `mygroup/cind` |
| `IMAGE_TAG` | Remote tag (default `latest`) |
| `IMAGE_LOCAL` | Local Compose image name (default `cind:latest`) |

## Publish to GitLab Container Registry

```bash
# in .env
IMAGE_REGISTRY=registry.gitlab.com
IMAGE_REPOSITORY=mygroup/cind
IMAGE_TAG=latest

make build
make registry-login   # GitLab username + PAT (write_registry)
make publish
```

On another host:

```bash
make registry-login
make pull             # retags as cind:latest
make terminal-docker
```

Full details: [Makefile — Publish image to GitLab](makefile.md#publish-image-to-gitlab).

## Network

Compose uses the default project network.

The ttyd overlay publishes host port `TTYD_HOST_PORT` (default `7681`) to container port `7681`.
Open `http://localhost:7681` after `make terminal` or `make terminal-docker`.
