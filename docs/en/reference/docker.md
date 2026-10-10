# Docker and Compose

Use this page for image tags, Compose overlays, and `$ORCAN_DATA` binds. For **why** the split exists, see [Architecture](../architecture.md).

## Image

- Base: Debian Bookworm Slim
- Multi-stage tool fetch (Node, Go, Rust, uv)
- tmux **3.6a** from `tmux/tmux-builds` (not the bookworm 3.3a package)
- OpenSSH client and `sshpass` for explicitly password-authenticated SSH automation
- GitHub CLI (`gh`) and GitLab CLI (`glab`) on PATH for amd64 and arm64.
  Sign in inside the container with `gh auth login` or `glab auth login`;
  credentials are not built into the image. GitLab Self-Managed is also supported.
- Non-root user `developer`
- sbt includes only the native client for the image's Linux architecture;
  tool documentation is retained.
- Entry: `docker-entrypoint`

| Tag | Role |
| --- | --- |
| `orcan:latest` | Standard Orcan image used by Compose |
| `orcan:<VERSION>` | Versioned tag of that same image |

Agent choice:

| Flag | Effect |
| --- | --- |
| `--agent NAME` | Add one explicit client (`cursor`, `claude`, `codex`, `gemini`, `copilot`) |
| `--all-agents` | Install every supported client |

`/etc/orcan/agents.json` records the installed clients. `orcan status` and
`orcan doctor` display it. Gemini and Copilot data persist under
`ORCAN_DATA/gemini` and `ORCAN_DATA/copilot`.

Build-args: `INSTALL_CURSOR` / `INSTALL_CLAUDE` / `INSTALL_CODEX` /
`INSTALL_GEMINI` / `INSTALL_COPILOT`.
Version label: `ORCAN_VERSION` / `/etc/orcan/version`.

## Compose files

| File | Role |
| --- | --- |
| `docker-compose.yml` | Base service, `$ORCAN_DATA` binds, no Docker socket |
| `docker-compose.keepalive.yml` | `orcan-supervisord` with `ORCAN_SUPERVISOR_MODE=keepalive` — default `orcan up` (local-only; use `orcan enter`) |
| `docker-compose.docker.yml` | Host Docker socket + `DOCKER_GID` |
| `docker-compose.ttyd.yml` | `orcan-supervisord` with `ORCAN_SUPERVISOR_MODE=ttyd` when `orcan up --web-terminal`; published port (`TTYD_BIND`, default `0.0.0.0`), optional `TTYD_CREDENTIAL`, healthcheck |
| `mounts/compose-projects.generated.yml` | Path-parity project mounts (generated) |

Overlays for `orcan up --web-terminal` / `--docker-socket` / `--ssh` /
`--network` are opt-in. Capability ladder and risks: [Security](security.md).

ttyd: default publish is all interfaces (`TTYD_BIND=0.0.0.0`). **Recommended
remote access** is Tailscale (or another private VPN) plus
`TTYD_CREDENTIAL` / `--web-terminal-auth`. Set `TTYD_BIND=127.0.0.1` for
host-local only. `orcan url` prints `http://localhost:<port>` for wildcard
binds.

## Process layout (supervisord) { #process-layout-supervisord }

`orcan up` no longer uses bare `sleep infinity` / `cursor-ttyd` as the
Compose command. Both overlays run **`orcan-supervisord`**, which picks
programs from `/etc/orcan/supervisor.d/` into `/tmp/orcan-supervisor.d/`
and execs `supervisord -n`:

| `ORCAN_SUPERVISOR_MODE` | Foreground program | Typical access |
| --- | --- | --- |
| `keepalive` (default) | `sleep infinity` | `orcan enter` |
| `ttyd` | `cursor-ttyd` | browser |

| Program | Command |
| --- | --- |

**Logs** (durable on the history bind — survive recreate):

| Path (container) | Host |
| --- | --- |
| `~/.local/share/orcan/history/supervisor/` | `$ORCAN_DATA/history/supervisor/` |

| File | What |
| --- | --- |
| `supervisord.log` | Supervisor + startup banner |
| `childlog/ttyd.*.log` | Browser terminal (ttyd mode) |

## `$ORCAN_DATA` binds

Default host root: `~/.config/orcan`.

| Host | Container |
| --- | --- |
| `cursor/` | `~/.cursor` |
| `cursor-app/` | `~/.config/cursor` |
| `claude/` | `~/.claude` (`CLAUDE_CONFIG_DIR` — OAuth + settings survive restarts) |
| `codex/` | `~/.codex` |
| `cache/` | `~/.cache` (npm / pnpm / cargo / go / uv / … nest here via env) |
| `history/` | `~/.local/share/orcan/history` (`HISTFILE`; per-workspace files under `history/workspaces/<name>/` in tmux) |
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

### GitLab CLI

The image includes a pinned `glab` release for amd64 and arm64. Use
`orcan up --gitlab [--gitlab-hostname HOST]` to supply host authentication only
when requested. See [GitLab access](cli.md#gitlab-access). Existing images need
an update/rebuild to include the new tool; enabling access does not install it
inside a running container.
