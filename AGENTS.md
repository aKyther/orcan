# AGENTS.md

## Purpose

This repository builds and runs an isolated Docker environment for Cursor CLI.
A single host project is mounted at `/workspace`. Agents must treat that mount as the only writable project scope.

## File map

| Path | Role |
| --- | --- |
| `Dockerfile` | Image build only (packages, COPY rootfs, user, ENTRYPOINT) |
| `docker-compose.yml` | Base service (no Docker socket) |
| `docker-compose.docker.yml` | Optional Docker socket overlay |
| `docker-compose.ssh.yml` | Optional OpenSSH overlay (VPS / Tailscale) |
| `Makefile` | Thin host UI; calls Compose and `scripts/repository/` |
| `docker/rootfs/` | Files installed into the image (source of truth) |
| `scripts/repository/` | Host-only helpers (`update-env`, `validate`) |
| `tests/smoke/` | Container smoke tests |
| `.env.example` | Safe defaults for UID/GID and `PROJECT_DIR` |
| `.cursorignore` | Blocks agent access to secrets and junk **in this repo** |
| `.cursorindexingignore` | Reduces indexing noise |
| `.cursor/rules/*.mdc` | Cursor rules **for this repository** |
| `docs/` | MkDocs Material documentation |
| `mkdocs.yml` | Docs site config |

## Separation rules

- Repository docs/rules (root `.cursor/`, `AGENTS.md`) ≠ image defaults (`docker/rootfs/opt/cursor-defaults/`).
- Container scripts live only under `docker/rootfs/usr/local/bin/`.
- Host scripts live only under `scripts/repository/`.
- Do not embed large heredoc programs in the Dockerfile.

## Commands

```bash
make env
make build
make shell
make shell-docker
make up
make up-docker
make up-ssh
make up-ssh-docker
make down
make logs
make rebuild
make clean
make clean-volumes
make config
make init-project
make init-project-dry-run
make validate
make test
make docs
make docs-serve
make help
```

Use `PROJECT_DIR=/absolute/path/to/project` to choose the mounted project.

## Cursor defaults

- Source of truth: `docker/rootfs/opt/cursor-defaults/` → `/opt/cursor-defaults`.
- Seed `${HOME}/.cursor` at startup via `init-cursor-home` (missing files only).
- Do not write defaults only into `/home/.../.cursor` during `docker build` (volume hides them).
- Do not auto-modify `/workspace` on startup; use `cursor-init-project` explicitly.
- Active CLI permissions file is `cli-config.json`.

## Dockerfile rules

- Keep Debian Bookworm Slim as the final base.
- Keep multi-stage copies for Node, Go, Rust, and uv.
- Keep non-root user `developer`.
- Copy container files from `docker/rootfs/`.
- Never bake secrets, tokens, or SSH keys into the image.
- Prefer `--no-install-recommends` and clean APT lists.
- Support `amd64` and `arm64` when practical.
- Do not grow the image without a clear reason.

## Compose rules

- Base file must work without `/var/run/docker.sock`.
- Docker socket and `group_add` belong only in `docker-compose.docker.yml`.
- OpenSSH publish/password settings belong only in `docker-compose.ssh.yml`.
- Keep named volumes for caches and Cursor config.
- Mount only the selected project at `/workspace`.
- Do not mount `/`, `/home`, or `/etc`.

## Makefile rules

- Use `docker compose` (v2 plugin).
- Keep the Makefile thin; put host logic in `scripts/repository/`.
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

1. `make validate`
2. `make build` when Docker is available
3. `make test` when Docker is available
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

- [ ] `make validate` passes
- [ ] Compose config validates (base and docker overlay)
- [ ] Makefile help matches real targets
- [ ] Docs/README updated for interface/path changes
- [ ] No secrets added to the image or repo
- [ ] Final report lists ran tests, skipped tests, and limits
