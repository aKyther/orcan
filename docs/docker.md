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
| `docker/rootfs/usr/local/bin/cursor-sshd` | `/usr/local/bin/cursor-sshd` | Foreground OpenSSH (SSH overlay) |
| `docker/rootfs/etc/ssh/sshd_config.d/cursor.conf` | `/etc/ssh/sshd_config.d/cursor.conf` | SSH daemon settings |
| `docker/rootfs/etc/skel/.tmux.conf` | `/home/developer/.tmux.conf` | TMUX config |
| `docker/rootfs/etc/skel/.vimrc` | `/home/developer/.vimrc` | Vim config |
| `docker/rootfs/etc/skel/.bashrc.d/` | `/home/developer/.bashrc.d/` | Interactive shell setup |
| `docker/rootfs/etc/profile.d/cursor-dev-path.sh` | `/etc/profile.d/cursor-dev-path.sh` | Toolchain PATH |
| `scripts/repository/` | *(not in image)* | Host-only helpers |

See also `docker/README.md` in the repository.

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
4. Install Cursor CLI as that user.
5. Set `ENTRYPOINT` / `CMD`.

!!! note

    The runtime user is non-root. `sudo` is available inside the container for package installs during a session.

## Compose files

### `docker-compose.yml` (base)

Provides:

* project bind mount at `/workspace`
* named volumes for caches and Cursor config
* read-only `~/.gitconfig` and `~/.ssh`
* resource limits and a `/tmp` tmpfs
* `no-new-privileges`

Does **not** mount the Docker socket.

### `docker-compose.docker.yml` (overlay)

Adds:

* `/var/run/docker.sock`
* `group_add: DOCKER_GID`

### `docker-compose.ssh.yml` (overlay)

Runs OpenSSH for remote access (for example a VPS behind Tailscale):

* `command: cursor-sshd`
* publishes `${SSH_HOST_PORT:-22}:22`
* sets `DEVELOPER_PASSWORD` (default `cursor`)
* clears `no-new-privileges` so `sudo` can start `sshd`
* does **not** bind-mount host `~/.ssh` or `~/.gitconfig`
* `restart: unless-stopped`

```bash
make up-ssh
ssh developer@<tailscale-ip>
```

Default login: user `developer`, password `cursor`.

!!! warning

    Use password auth only on a private network (Tailscale).
    Host port 22 conflicts with a host `sshd` — change `SSH_HOST_PORT` or stop the host daemon.

## Layout

```text
Host
└── PROJECT_DIR
     │
     ▼
Container
├── /workspace
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
| `cursor-config` | `/home/developer/.cursor` | Persist Cursor CLI config/login |
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

Matching host UID/GID prevents root-owned files in your project tree.

## TMUX and Vim

Interactive shells source `~/.bashrc.d/50-cursor-dev.sh`, which may start TMUX when:

* `tmux` exists
* `TMUX` is unset
* stdin is a TTY

Session name: `cursor`.

Config sources:

| Repo file | Container path |
| --- | --- |
| `docker/rootfs/etc/skel/.tmux.conf` | `/home/developer/.tmux.conf` |
| `docker/rootfs/etc/skel/.vimrc` | `/home/developer/.vimrc` |

## Cursor defaults volume

`cursor-config` mounts at `/home/developer/.cursor`.

Defaults live in `/opt/cursor-defaults` and are copied in at startup when missing.
See [Cursor](cursor.md).

## Environment variables

| Variable | Role |
| --- | --- |
| `PROJECT_DIR` | Host path mounted at `/workspace` |
| `USER_UID` / `USER_GID` | Container user identity |
| `DOCKER_GID` | Socket group for `*-docker` targets |
| `CPUS` / `MEMORY` / `SHM_SIZE` / `TMPFS_SIZE` | Resource limits |
| `SSH_HOST_PORT` | Host port published for SSH overlay (default `22`) |
| `DEVELOPER_PASSWORD` | Password for user `developer` in SSH overlay (default `cursor`) |

## Network

Compose uses the default project network. No extra published ports are required for a shell workflow.

The SSH overlay publishes host port `SSH_HOST_PORT` (default `22`) to container port `22`.
