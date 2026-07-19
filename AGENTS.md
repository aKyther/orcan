# AGENTS.md

## Purpose

This repository builds and runs an isolated Docker environment for Cursor CLI.
A single host project is mounted at `/workspace`. Agents must treat that mount as the only writable project scope.

## File map

| Path | Role |
| --- | --- |
| `Dockerfile` | Multi-stage image: tools + Cursor CLI |
| `docker-compose.yml` | Base service (no Docker socket) |
| `docker-compose.docker.yml` | Optional Docker socket overlay |
| `Makefile` | User entrypoints (`build`, `shell`, `shell-docker`, …) |
| `cursor-home/` | Defaults installed to `/opt/cursor-defaults` |
| `scripts/` | `docker-entrypoint`, `init-cursor-home`, `cursor-init-project` |
| `.tmux.conf` | TMUX config copied into the image home |
| `.vimrc` | Vim config copied into the image home |
| `.env.example` | Safe defaults for UID/GID and `PROJECT_DIR` |
| `.cursorignore` | Blocks agent access to secrets and junk |
| `.cursorindexingignore` | Reduces indexing noise |
| `.cursor/rules/*.mdc` | Cursor-specific always-on and scoped rules |
| `docs/` | MkDocs Material documentation |
| `mkdocs.yml` | Docs site config |

## Commands

```bash
make env
make build
make shell
make shell-docker
make up
make up-docker
make down
make logs
make rebuild
make clean
make clean-volumes
make config
make init-project
make init-project-dry-run
make help
```

Use `PROJECT_DIR=/absolute/path/to/project` to choose the mounted project.

## Cursor defaults

- Store immutable defaults in `/opt/cursor-defaults` (from `cursor-home/`).
- Seed `${HOME}/.cursor` at startup via `init-cursor-home` (missing files only).
- Do not write defaults only into `/home/.../.cursor` during `docker build` (volume hides them).
- Do not auto-modify `/workspace` on startup; use `cursor-init-project` explicitly.
- Active CLI permissions file is `cli-config.json`, not a fictional `permissions.json`.

## Dockerfile rules

- Keep Debian Bookworm Slim as the final base.
- Keep multi-stage copies for Node, Go, Rust, and uv.
- Keep non-root user `developer`.
- Never bake secrets, tokens, or SSH keys into the image.
- Prefer `--no-install-recommends` and clean APT lists.
- Support `amd64` and `arm64` when practical.
- Do not grow the image without a clear reason.

## Compose rules

- Base file must work without `/var/run/docker.sock`.
- Docker socket and `group_add` belong only in `docker-compose.docker.yml`.
- Keep named volumes for caches and Cursor config.
- Mount only the selected project at `/workspace`.
- Do not mount `/`, `/home`, or `/etc`.

## Makefile rules

- Use `docker compose` (v2 plugin).
- Derive `USER_UID` / `USER_GID` from the host.
- Derive `DOCKER_GID` from the socket when present; fall back to `999`.
- `down` and `clean` must not delete named volumes.
- `clean-volumes` is destructive and must stay explicit.
- Keep `help` accurate when targets change.

## Security model

- Isolation is best-effort. The bind-mounted project is writable on the host.
- Docker socket access is host-level privilege. Use only `*-docker` targets when needed.
- `sudo` inside the container is root in the container, not a full host escape by itself.
- Secrets stay out of the image and out of git (`.env` is ignored).

## Required validation

After infrastructure changes:

1. `make config` or `docker compose … config`
2. `make help`
3. `make build` when Docker is available
4. Smoke-check key tools in a running container when a build succeeds

## Agent boundaries

Allowed:

- Edit files under `/workspace` for this repository.
- Run Make, Compose config checks, and image builds.
- Update docs when the user-facing interface changes.

Not allowed:

- Read or edit host paths outside `/workspace`.
- Modify `.env` unless asked.
- Run `docker system prune`.
- Delete volumes except via an explicit user request for `make clean-volumes`.
- Start `--privileged` containers.
- Mount sensitive host directories.
- Claim build success without running the build.

## Done checklist

- [ ] Compose config validates (base and docker overlay)
- [ ] Makefile help matches real targets
- [ ] Docs/README updated for interface changes
- [ ] No secrets added to the image or repo
- [ ] Final report lists ran tests, skipped tests, and limits
