# Makefile reference

Everyday commands for building and running the orcan container.

## Core targets

| Target | Description |
| --- | --- |
| `make help` | List all targets |
| `make setup` | **First run:** scaffold config (if missing), `make env`, show layout |
| `make env` | Refresh `.env`, runtime config, and project mounts from `orcan.config.json` |
| `make config-show` | Print config and generated runtime manifest |
| `make config-wizard` | Interactive create/edit `orcan.config.json` |
| `make config-init` | Copy example JSON template |
| `make config-scaffold` | Non-interactive add project from `PROJECT_DIR` |
| `make path-check` | Show mounts and workspace layout (read-only) |
| `make build` | Build **full** image (Claude + Cursor) → `orcan:latest` |
| `make build-claude` | Build **Claude-only** image → `orcan:claude` |
| `make rebuild` | Rebuild full without cache |
| `make rebuild-claude` | Rebuild Claude-only without cache |
| `make registry-show` | Show local/remote image names for publish |
| `make registry-login` | `docker login` to GitLab (or other) registry |
| `make publish` | Tag + push image to registry |
| `make pull` | Pull published image and retag as `orcan:latest` |
| `make terminal` | Start browser terminal (no Docker socket; does not run `make env`) |
| `make terminal-docker` | Start browser terminal with host Docker socket (does not run `make env`) |
| `make terminal-url` | Print browser terminal URL |
| `make down` | Stop containers |
| `make logs` | Follow container logs |
| `make validate` | Validate repository layout and scripts |
| `make test` | Run smoke tests |
| `make init-project` | Bootstrap Cursor/Claude files in `PROJECT_DIR` |
| `make init-project-dry-run` | Preview bootstrap for `PROJECT_DIR` |
| `make init-project-all` | Bootstrap every `projects[].path` (missing-only; not at startup) |
| `make init-project-all-dry-run` | Preview bootstrap for every configured project |

## Starting the terminal

`make terminal` and `make terminal-docker` **only start containers**. They do not run `make env`, regenerate `.orcan/*`, or overwrite `.env`.

```bash
make terminal
# or with Docker-from-Docker:
make terminal-docker
```

### Config change ritual

```bash
make config-wizard          # or edit orcan.config.json / config-scaffold
make env
make init-project-all       # optional: seed ignores / AGENTS in new repos
make down && make terminal-docker
```

First time (or missing `.env`):

```bash
make setup PROJECT_DIR=/absolute/path/to/repo
# or: make config-wizard && make env
make build
make terminal-docker
```

Daily use (no config change):

```bash
make terminal-docker
```

`make terminal` prints the URL (default `http://localhost:7681`). Run `make terminal-url` to print it again.

## Publish image to GitLab

Build once, push to GitLab Container Registry, pull on another host (e.g. VPS).

### 1. Configure `.env`

```dotenv
IMAGE_REGISTRY=registry.gitlab.com
IMAGE_REPOSITORY=mygroup/orcan
IMAGE_TAG=latest
```

Self-hosted GitLab: set `IMAGE_REGISTRY` to your registry host (often `registry.example.com`).

### 2. Log in

Create a GitLab **Personal Access Token** (or Deploy Token) with `read_registry` + `write_registry`.

```bash
make registry-login
# prompts for username + token
```

Non-interactive:

```bash
REGISTRY_USER=myuser REGISTRY_PASSWORD=glpat-... make registry-login
```

### 3. Build and push

```bash
make build
make publish
```

### 4. On another machine

```bash
# same IMAGE_* in .env
make registry-login
make pull
make terminal-docker
```

Check names anytime:

```bash
make registry-show
```

### After config changes

```bash
make config-wizard
# or: make config-scaffold PROJECT_DIR=... WORKSPACE=...
make env
make down && make terminal-docker
```

## Compose stacks

| Target | Compose files |
| --- | --- |
| `make terminal` | `docker-compose.yml` + `.orcan/compose-projects.generated.yml` + `docker-compose.ttyd.yml` |
| `make terminal-docker` | above + `docker-compose.docker.yml` |

Project paths come from `orcan.config.json` → `.orcan/compose-projects.generated.yml`.
Run `make env` after changing projects (wizard, scaffold, or hand-edit).

## Config helpers

| Target | Description |
| --- | --- |
| `make setup` | First run: scaffold config if missing, run `env`, show next steps |
| `make config-wizard` | Interactive create/edit `orcan.config.json` (keep / change / delete) |
| `make config-scaffold` | Non-interactive append workspace/project from `PROJECT_DIR` |
| `make config-show` | Print config and generated runtime manifest |
| `make config-init` | Optional: copy full `orcan.config.example.json` template |

```bash
make config-wizard
# or:
make setup PROJECT_DIR=/home/you/projects/my-app
make build
make terminal-docker
```

Add repos without the wizard:

```bash
make config-scaffold PROJECT_DIR=/home/you/gotibooks/backend WORKSPACE=gotibooks
make config-scaffold PROJECT_DIR=/home/you/gotibooks/frontend WORKSPACE=gotibooks
make env
```

Optional: `WORKSPACE=my-name`, `FORCE=1`.

Note: `make config` prints **Docker Compose** config, not `orcan.config.json`.

## Docker socket

`make terminal-docker` fails early if `/var/run/docker.sock` is absent.

Use it only when you need `docker compose` or `docker build` inside the container with host path parity.

## Other targets

| Target | Description |
| --- | --- |
| `make config` | Print resolved Compose config |
| `make init-project` | Bootstrap Cursor/Claude files in `PROJECT_DIR` |
| `make init-project-dry-run` | Preview bootstrap |
| `make init-project-all` | Bootstrap every configured project path |
| `make init-project-all-dry-run` | Preview all-project bootstrap |
| `make clean` | Stop containers, keep host data under `ORCAN_DATA` |
| `make clean-data` | Delete `$ORCAN_DATA` (`~/.config/orcan`) — login + caches |
| `make clean-volumes` | Alias for `clean-data` |
| `make docs` | Build documentation site |
| `make test-path-parity` | Integration test for path parity + Docker socket |

## Renamed targets (migration)

| Old | New |
| --- | --- |
| `make shell` | `make terminal` |
| `make shell-docker` | `make terminal-docker` |
| `make terminal` (URL only) | `make terminal-url` |
