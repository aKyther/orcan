# Docker

This page explains the image, Compose files, volumes, and runtime user.

## Why Docker is used

Docker keeps the toolchain inside an image. Your host package manager stays clean. Every machine that builds this image gets the same tools.

## Dockerfile

The image is multi-stage:

| Stage | Source | Purpose |
| --- | --- | --- |
| `node-tools` | `node:22-bookworm-slim` | Node, npm, pnpm |
| `go-tools` | `golang:1.24-bookworm` | Go toolchain |
| `rust-tools` | `rust:1-bookworm` | Rustup / Cargo |
| `uv-tools` | `ghcr.io/astral-sh/uv:latest` | `uv` / `uvx` |
| final | `debian:bookworm-slim` | Runtime image |

The final stage installs base packages, copies toolchains, installs Docker CLI plugins, creates user `developer`, then installs Cursor CLI.

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

Makefile targets with the `-docker` suffix apply both files.

## Layout

```text
Host
└── PROJECT_DIR
     │
     ▼
Container
├── /workspace
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
| `cursor-cache` | `/home/developer/.cache` | General caches (includes uv/go build cache paths) |
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

`.bashrc` starts TMUX when:

* `tmux` exists
* `TMUX` is unset
* stdin is a TTY

Session name: `cursor`.

The image copies tracked config files from the repo:

| Repo file | Container path |
| --- | --- |
| `.tmux.conf` | `/home/developer/.tmux.conf` |
| `.vimrc` | `/home/developer/.vimrc` |

Edit those files in the repository, then rebuild the image to apply changes.

## Environment variables

| Variable | Role |
| --- | --- |
| `PROJECT_DIR` | Host path mounted at `/workspace` |
| `USER_UID` / `USER_GID` | Container user identity |
| `DOCKER_GID` | Socket group for `*-docker` targets |
| `CPUS` / `MEMORY` / `SHM_SIZE` / `TMPFS_SIZE` | Resource limits |

## Cursor defaults volume

`cursor-config` mounts at `/home/developer/.cursor`.

Defaults live in `/opt/cursor-defaults` and are copied in at startup when missing.
See [Cursor](cursor.md).

## Network

Compose uses the default project network. No extra published ports are required for a shell workflow.
