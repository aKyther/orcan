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
| `docker/rootfs/etc/profile.d/cursor-dev-path.sh` | `/etc/profile.d/cursor-dev-path.sh` | Toolchain PATH |
| `scripts/repository/` | *(not in image)* | Host-only helpers |

## Image filesystem (`docker/rootfs/`)

Files under `docker/rootfs/` are copied into the container image.
Their paths match the final container layout.

```text
docker/rootfs/
├── etc/
│   ├── profile.d/cursor-dev-path.sh
│   └── skel/
│       ├── .bashrc.d/50-cursor-dev.sh
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
* Runtime writable state lives in `${HOME}/.cursor` (named volume).

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

Provides:

* project bind mounts from `cind.config.json` (path parity + workspace roots)
* named volumes for caches and Cursor config
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
Host
└── PROJECT_DIR
     │
     ▼
Container
├── ${PROJECT_DIR}                 (bind mount, path parity)
├── /opt/cursor-defaults
├── /home/developer/.cursor      (volume)
├── /home/developer/.cache       (volume)
├── /home/developer/.npm         (volume)
├── /home/developer/.local/share/pnpm  (volume)
├── /home/developer/.cargo       (volume)
├── /home/developer/go           (volume)
└── /command-history             (volume)
```

## Volumes

| Volume | Path | Why |
| --- | --- | --- |
| `cursor-config` | `/home/developer/.cursor` | Cursor CLI config, chats, rules, skills |
| `cursor-app-config` | `/home/developer/.config/cursor` | Cursor login (`auth.json`) |
| `cursor-cache` | `/home/developer/.cache` | General caches |
| `npm-cache` | `/home/developer/.npm` | npm cache |
| `pnpm-cache` | `/home/developer/.local/share/pnpm` | pnpm store/home |
| `cargo-cache` | `/home/developer/.cargo` | Cargo registry and binaries |
| `go-cache` | `/home/developer/go` | GOPATH modules and bins |
| `bash-history` | `/command-history` | Shared bash history file |

Named volumes survive `make down` and `make clean`.
Only `make clean-volumes` deletes them.

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

Interactive shells inside TMUX source `~/.bashrc.d/50-cursor-dev.sh` (aliases, PATH, `cd` to `PROJECT_DIR`).

## Cursor defaults volume

`cursor-config` mounts at `/home/developer/.cursor`.

Defaults live in `/opt/cursor-defaults` and are copied in at startup when missing.
See [Cursor](cursor.md).

## Environment variables

| Variable | Role |
| --- | --- |
| `PROJECT_DIR` | Absolute host project path (same path inside the container) |
| `USER_UID` / `USER_GID` | Container user identity |
| `DOCKER_GID` | Socket group for `*-docker` targets |
| `CPUS` / `MEMORY` / `SHM_SIZE` / `TMPFS_SIZE` | Resource limits |
| `TTYD_PORT` | Container port for ttyd (default `7681`) |
| `TTYD_HOST_PORT` | Host port published for the browser terminal (default `7681`) |
| `TMUX_SESSION_NAME` | TMUX session name in the browser terminal (default `workspace`) |
| `IMAGE_REGISTRY` | Registry host for publish/pull (default `registry.gitlab.com`) |
| `IMAGE_REPOSITORY` | Path under registry, e.g. `mygroup/cind` |
| `IMAGE_TAG` | Remote tag (default `latest`) |
| `IMAGE_LOCAL` | Local Compose image name (default `cursor-dev:latest`) |

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
make pull             # retags as cursor-dev:latest
make terminal-docker
```

Full details: [Makefile — Publish image to GitLab](makefile.md#publish-image-to-gitlab).

## Network

Compose uses the default project network.

The ttyd overlay publishes host port `TTYD_HOST_PORT` (default `7681`) to container port `7681`.
Open `http://localhost:7681` after `make terminal` or `make terminal-docker`.
