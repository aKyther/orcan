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
| `docker/rootfs/etc/skel/.zshrc` + `.zshrc.d/` | `/home/developer/.zshrc*` | Default interactive shell (zsh + plugins + Starship) |
| `docker/rootfs/etc/skel/.bashrc.d/` | `/home/developer/.bashrc.d/` | Bash fallback snippets |
| `docker/rootfs/etc/profile.d/orcan-path.sh` | `/etc/profile.d/orcan-path.sh` | Toolchain PATH (login shells) |
| `docker/rootfs/opt/orcan/gitconfig` | seeded → `~/.gitconfig` | Container-local git defaults (delta) |
| `docker/rootfs/opt/orcan/starship.toml` | seeded → `~/.config/starship.toml` | Prompt defaults |
| `scripts/repository/` | *(not in image)* | Host-only helpers |

## Image filesystem (`docker/rootfs/`)

Files under `docker/rootfs/` are copied into the container image.
Their paths match the final container layout.

```text
docker/rootfs/
├── etc/
│   ├── orcan/shell/aliases.sh
│   ├── profile.d/orcan-path.sh
│   └── skel/
│       ├── .zshrc
│       ├── .zshrc.d/   (PATH, aliases, plugins, starship)
│       ├── .bashrc.d/  (bash fallback)
│       ├── .tmux.conf
│       └── .vimrc
├── opt/
│   ├── orcan/            → gitconfig + starship.toml seeds
│   └── cursor-defaults/ → /opt/cursor-defaults
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
* Runtime writable state lives in `${HOME}/.cursor` (host: `$ORCAN_DATA/cursor`).

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

Always in the image (no extra pip packages required for orcan scripts):

| Tool | Notes |
| --- | --- |
| `python` / `python3` | Debian Bookworm (`python-is-python3`) |
| `pip3` / `python3-venv` / `python3-dev` | System installs and building wheels |
| `uv` / `uvx` | Preferred for project deps (`uv add`, `uv run`) |

`orcan-ai-statusline` and tmux AI usage use **stdlib only** (`json`, `pathlib`, …). For project libraries, prefer `uv` in the workspace rather than `pip install` into the system Python.

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

Service name: **`orcan`**, image: **`orcan:latest`**.

Provides:

* project bind mounts from `orcan.config.json` (path parity + workspace roots)
* host binds under `ORCAN_DATA` (`~/.config/orcan`) for Cursor/Claude state and caches
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
* sets `TTYD_PORT`, `TTYD_FONT_SIZE`, `TTYD_THEME`, workspace env vars
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
Host ~/.config/orcan/                 Container
────────────────────────────────     ─────────────────────────────────
cursor/           ───────────────►   /home/developer/.cursor
cursor-app/       ───────────────►   /home/developer/.config/cursor
claude/           ───────────────►   /home/developer/.claude
cache/            ───────────────►   /home/developer/.cache
npm/              ───────────────►   /home/developer/.npm
pnpm/             ───────────────►   /home/developer/.local/share/pnpm
cargo/            ───────────────►   /home/developer/.cargo
go/               ───────────────►   /home/developer/go
shell-history/    ───────────────►   /command-history  (.zsh_history)
```

Plus path-parity project mounts and `/opt/cursor-defaults` from the image.

## Host data (`ORCAN_DATA`)

Always on — same idea as poetry (`~/.config/pypoetry`) or pip: product state lives under the user’s config home.

Default path: **`$HOME/.config/orcan`**.

`make env` (and first `make setup`):

1. Writes absolute `ORCAN_DATA=…` into `.env` if missing/empty
2. Creates the subdirectory tree (`cursor`, `claude`, caches, …)
3. Sets ownership to `USER_UID`/`USER_GID`

Override only when you need another location:

```dotenv
ORCAN_DATA=/custom/path/orcan
```

| Host path | Container path | Why |
| --- | --- | --- |
| `$ORCAN_DATA/cursor` | `/home/developer/.cursor` | Cursor CLI config, chats, rules, skills |
| `$ORCAN_DATA/cursor-app` | `/home/developer/.config/cursor` | Cursor login (`auth.json`) |
| `$ORCAN_DATA/claude` | `/home/developer/.claude` | Claude Code login and state |
| `$ORCAN_DATA/cache` | `/home/developer/.cache` | General caches |
| `$ORCAN_DATA/npm` | `/home/developer/.npm` | npm cache |
| `$ORCAN_DATA/pnpm` | `/home/developer/.local/share/pnpm` | pnpm store/home |
| `$ORCAN_DATA/cargo` | `/home/developer/.cargo` | Cargo registry and binaries |
| `$ORCAN_DATA/go` | `/home/developer/go` | GOPATH modules and bins |
| `$ORCAN_DATA/shell-history` | `/command-history` | Shared zsh history (`.zsh_history`) |

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

The browser launcher (`cursor-ttyd` → `cursor-launcher`) creates **one tmux session per workspace** (`workspaces[].name`). Working directory is `/home/developer/workspaces/<name>/`.

Config sources:

| Repo file | Container path |
| --- | --- |
| `docker/rootfs/etc/skel/.tmux.conf` | `/home/developer/.tmux.conf` |
| `docker/rootfs/etc/skel/.vimrc` | `/home/developer/.vimrc` |

Interactive shells inside TMUX are **zsh** (`default-shell`). They source `~/.zshrc.d/` (PATH, workspace `cd`, aliases from `/etc/orcan/shell/aliases.sh`, autosuggestions/syntax-highlighting/fzf, Starship). Bash snippets remain for manual `bash` sessions.

Git: `~/.gitconfig` is seeded missing-only from `/opt/orcan/gitconfig` (delta pager). Set `user.name` / `user.email` inside the container — host gitconfig is not mounted.

Switch sessions: `Ctrl+Space w`. Details: [tmux](tmux.md).

## Cursor defaults on host data

`$ORCAN_DATA/cursor` mounts at `/home/developer/.cursor`.

Defaults live in `/opt/cursor-defaults` and are copied in at startup when missing.
See [Cursor](cursor.md).

## Image variants

One Dockerfile, two tags:

| Tag | Build | Contents |
| --- | --- | --- |
| `orcan:latest` (also `orcan:full`) | `make build` | Claude Code + Cursor (`agent`) |
| `orcan:claude` | `make build-claude` | Claude Code only |

```bash
make build                 # Claude + Cursor → orcan:latest
make build-claude          # Claude only → orcan:claude

# Run Claude-only:
IMAGE_LOCAL=orcan:claude make terminal-docker
```

Bake-time flag: `INSTALL_CURSOR=0|1` (Compose build arg). Runtime file: `/etc/orcan/variant` (`full` or `claude`).

## Environment variables

| Variable | Role |
| --- | --- |
| `PROJECT_DIR` | Absolute host project path (same path inside the container) |
| `ORCAN_DATA` | Host data root (default `$HOME/.config/orcan`) |
| `USER_UID` / `USER_GID` | Container user identity |
| `DOCKER_GID` | Socket group for `*-docker` targets |
| `TZ` | Timezone (`make env` copies host zone, e.g. `Europe/Warsaw`); `/etc/localtime` is bind-mounted read-only |
| `CPUS` / `MEMORY` / `SHM_SIZE` / `TMPFS_SIZE` | Resource limits |
| `TTYD_PORT` | Container port for ttyd (default `7681`) |
| `TTYD_HOST_PORT` | Host port published for the browser terminal (default `7681`) |
| `IMAGE_REGISTRY` | Registry host for publish/pull (default `registry.gitlab.com`) |
| `IMAGE_REPOSITORY` | Path under registry, e.g. `mygroup/orcan` |
| `IMAGE_TAG` | Remote tag (default `latest`) |
| `IMAGE_LOCAL` | Local Compose image name (default `orcan:latest`; use `orcan:claude` for Claude-only) |
| `INSTALL_CURSOR` | Build arg: `1` = full, `0` = Claude-only |

## Publish to GitLab Container Registry

```bash
# in .env
IMAGE_REGISTRY=registry.gitlab.com
IMAGE_REPOSITORY=mygroup/orcan
IMAGE_TAG=latest

make build
make registry-login   # GitLab username + PAT (write_registry)
make publish
```

On another host:

```bash
make registry-login
make pull             # retags as orcan:latest
make terminal-docker
```

Full details: [Makefile — Publish image to GitLab](makefile.md#publish-image-to-gitlab).

## Network

Compose uses the default project network.

The ttyd overlay publishes host port `TTYD_HOST_PORT` (default `7681`) to container port `7681`.
Open `http://localhost:7681` after `make terminal` or `make terminal-docker`.
