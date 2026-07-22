# Makefile reference

Everyday commands for building and running the cind container.

## Core targets

| Target | Description |
| --- | --- |
| `make help` | List all targets |
| `make setup` | **First run:** scaffold config (if missing), `make env`, show layout |
| `make env` | Refresh `.env`, runtime config, and project mounts from `cind.config.json` |
| `make config-init` | Create `cind.config.json` from example (skip if exists) |
| `make config-scaffold` | Add workspace/project from `PROJECT_DIR` into `cind.config.json` |
| `make config-show` | List workspaces (config + runtime manifest) |
| `make path-check` | Show mounts and workspace layout (read-only) |
| `make build` | Build the container image (needs `.env` only) |
| `make rebuild` | Rebuild without cache (needs `.env` only) |
| `make registry-show` | Show local/remote image names for publish |
| `make registry-login` | `docker login` to GitLab (or other) registry |
| `make publish` | Tag + push image to registry |
| `make pull` | Pull published image and retag as `cind:latest` |
| `make terminal` | Start browser terminal (no Docker socket; does not run `make env`) |
| `make terminal-docker` | Start browser terminal with host Docker socket (does not run `make env`) |
| `make terminal-url` | Print browser terminal URL |
| `make down` | Stop containers |
| `make logs` | Follow container logs |
| `make validate` | Validate repository layout and scripts |
| `make test` | Run smoke tests |

## Starting the terminal

`make terminal` and `make terminal-docker` **only start containers**. They do not run `make env`, regenerate `.cind/*`, or overwrite `.env`.

```bash
make terminal
# or with Docker-from-Docker:
make terminal-docker
```

Run **`make env`** when you change `cind.config.json`, add a project, or need fresh generated mounts — then `make terminal-docker` again.

First time (or missing `.env`):

```bash
make setup PROJECT_DIR=/absolute/path/to/repo
make build
make terminal-docker
```

Daily use:

```bash
make terminal-docker
```

`make terminal` prints the URL (default `http://localhost:7681`). Run `make terminal-url` to print it again.

## Publish image to GitLab

Build once, push to GitLab Container Registry, pull on another host (e.g. VPS).

### 1. Configure `.env`

```dotenv
IMAGE_REGISTRY=registry.gitlab.com
IMAGE_REPOSITORY=mygroup/cind
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
make config-scaffold PROJECT_DIR=/home/you/gotibooks/frontend WORKSPACE=gotibooks
make env
make down && make terminal-docker
```

### With JSON config

```bash
make env
make terminal-docker
```

## Compose stacks

| Target | Compose files |
| --- | --- |
| `make terminal` | `docker-compose.yml` + `.cind/compose-projects.generated.yml` + `docker-compose.ttyd.yml` |
| `make terminal-docker` | above + `docker-compose.docker.yml` |

Project paths come from `cind.config.json` → `.cind/compose-projects.generated.yml`.
Run `make env` after changing projects.

## JSON config helpers

| Target | Description |
| --- | --- |
| `make setup` | First run: create minimal `cind.config.json`, run `env`, show next steps |
| `make config-scaffold` | Append workspace/project from `PROJECT_DIR` |
| `make config-show` | Print `cind.config.json` and generated runtime manifest |
| `make config-init` | Optional: copy full `cind.config.example.json` template |

```bash
make setup PROJECT_DIR=/home/you/projects/my-app
make build
make terminal-docker
```

Add repos:

```bash
make config-scaffold PROJECT_DIR=/home/you/gotibooks/backend WORKSPACE=gotibooks
make config-scaffold PROJECT_DIR=/home/you/gotibooks/frontend WORKSPACE=gotibooks
make env
```

Optional: `WORKSPACE=my-name`, `FORCE=1`.

Note: `make config` prints **Docker Compose** config, not `cind.config.json`.

## Docker socket

`make terminal-docker` fails early if `/var/run/docker.sock` is absent.

Use it only when you need `docker compose` or `docker build` inside the container with host path parity.

## Other targets

| Target | Description |
| --- | --- |
| `make config` | Print resolved Compose config |
| `make init-project` | Bootstrap Cursor files in `PROJECT_DIR` |
| `make init-project-dry-run` | Preview bootstrap |
| `make clean` | Stop containers, keep host data under `CIND_DATA` |
| `make clean-data` | Delete `$CIND_DATA` (`~/.config/cind`) — login + caches |
| `make clean-volumes` | Alias for `clean-data` |
| `make docs` | Build documentation site |
| `make test-path-parity` | Integration test for path parity + Docker socket |

## Renamed targets (migration)

| Old | New |
| --- | --- |
| `make shell` | `make terminal` |
| `make shell-docker` | `make terminal-docker` |
| `make terminal` (URL only) | `make terminal-url` |
