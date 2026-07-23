# Docker and Compose

Use this page for image tags, Compose overlays, and `$ORCAN_DATA` binds. For **why** the split exists, see [Architecture](../architecture.md).

## Image

- Base: Debian Bookworm Slim
- Multi-stage tool fetch (Node, Go, Rust, uv)
- Non-root user `developer`
- Entry: `docker-entrypoint`
- Variants via build-arg `INSTALL_CURSOR` and file `/etc/orcan/variant`

| Tag | Build | Contents |
| --- | --- | --- |
| `orcan:latest` (+ `orcan:full`) | `make build` | Claude + Cursor |
| `orcan:claude` | `make build-claude` | Claude only |

Version label: `ORCAN_VERSION` / `/etc/orcan/version`.

## Compose files

| File | Role |
| --- | --- |
| `docker-compose.yml` | Base service, `$ORCAN_DATA` binds, no Docker socket |
| `docker-compose.docker.yml` | Host Docker socket + `DOCKER_GID` |
| `docker-compose.ttyd.yml` | `cursor-ttyd`, published port, healthcheck |
| `.orcan/compose-projects.generated.yml` | Path-parity project mounts (generated) |

## `$ORCAN_DATA` binds

Default host root: `~/.config/orcan`.

| Host | Container |
| --- | --- |
| `cursor/` | `~/.cursor` |
| `cursor-app/` | `~/.config/cursor` |
| `claude/` | `~/.claude` |
| `cache/`, `npm/`, `pnpm/`, `cargo/`, `go/` | Tool caches/homes |
| `shell-history/` | `/command-history` (zsh history) |

Named Docker volumes are **not** used for this data.

## Optional private registry

CI does **not** publish images. For your own registry see [Makefile — optional registry](makefile.md#optional-private-registry).
