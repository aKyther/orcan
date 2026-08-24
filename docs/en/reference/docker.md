# Docker and Compose

Use this page for image tags, Compose overlays, and `$ORCAN_DATA` binds. For **why** the split exists, see [Architecture](../architecture.md).

## Image

- Base: Debian Bookworm Slim
- Multi-stage tool fetch (Node, Go, Rust, uv)
- tmux **3.6a** from `tmux/tmux-builds` (not the bookworm 3.3a package)
- Non-root user `developer`
- Entry: `docker-entrypoint`

| Tag | Role |
| --- | --- |
| `orcan:latest` | Both agents — what Compose runs by default |
| `orcan:<VERSION>` | Same both-agents image (registry + local pin) |
| `orcan:<VERSION>-claude` | Local only — Claude Code installed, Cursor not |
| `orcan:<VERSION>-cursor` | Local only — Cursor CLI installed, Claude not |

Agent choice:

| Flag | Effect |
| --- | --- |
| (none) | Pull `orcan:<VERSION>` if available, else build both → `latest` + `<VERSION>` |
| `--claude` | No pull; build `orcan:<VERSION>-claude` (does not touch `latest`) |
| `--cursor` | No pull; build `orcan:<VERSION>-cursor` |

Then run single-agent images with `IMAGE_LOCAL=orcan:<VERSION>-claude orcan up` (or set `IMAGE_LOCAL` in `.env`). `/etc/orcan/variant` records `full` / `claude` / `cursor`. `orcan publish` only pushes both-agents tags.

Build-args: `INSTALL_CLAUDE` / `INSTALL_CURSOR` (default both `1`).
Version label: `ORCAN_VERSION` / `/etc/orcan/version`.

## Compose files

| File | Role |
| --- | --- |
| `docker-compose.yml` | Base service, `$ORCAN_DATA` binds, no Docker socket |
| `docker-compose.keepalive.yml` | `sleep infinity` — default `orcan up` (local-only; use `orcan enter`) |
| `docker-compose.docker.yml` | Host Docker socket + `DOCKER_GID` |
| `docker-compose.ttyd.yml` | `cursor-ttyd` when `orcan up --with-ttyd`; published port (`TTYD_BIND`, default `0.0.0.0`), optional `TTYD_CREDENTIAL`, healthcheck |
| `mounts/compose-projects.generated.yml` | Path-parity project mounts (generated) |

Overlays for `orcan up --with-ttyd` / `--with-docker` / `--with-git` /
`--with-network` are opt-in. Capability ladder and risks: [Security](security.md).

ttyd: default publish is all interfaces (`TTYD_BIND=0.0.0.0`). **Recommended
remote access** is Tailscale (or another private VPN) plus
`TTYD_CREDENTIAL` / `--with-ttyd-auth`. Set `TTYD_BIND=127.0.0.1` for
host-local only. `orcan url` prints `http://localhost:<port>` for wildcard
binds.

## `$ORCAN_DATA` binds

Default host root: `~/.config/orcan`.

| Host | Container |
| --- | --- |
| `cursor/` | `~/.cursor` |
| `cursor-app/` | `~/.config/cursor` |
| `claude/` | `~/.claude` (`CLAUDE_CONFIG_DIR` — OAuth + settings survive restarts) |
| `codex/` | `~/.codex` |
| `cache/` | `~/.cache` (npm / pnpm / cargo / go / uv / … nest here via env) |
| `history/` | `~/.local/share/orcan/history` (`HISTFILE`) |
| `dotfiles/` | `~/.config/orcan/dotfiles` |

Inside the container, `~/orcan-map/` is a symlink map (agents, cache, history,
dotfiles, workspaces) so the sandbox tree is easy to browse. Tools still
use their normal homes (`~/.cursor`, …).

Named Docker volumes are **not** used for this data.

Upgrading from an older `$ORCAN_DATA` layout (flat `npm/` / `shell-history/`
or nested `cache/cache/`): run
`bash scripts/migrations/consolidate-container-data.sh` on the host before
`orcan sync && orcan up`.

## Optional private registry

CI does **not** publish images. For your own registry use `orcan pull` / `orcan publish` (see [CLI reference](cli.md)). Maintainer helpers: [Makefile — optional registry](makefile.md#optional-private-registry).
