# Makefile reference

Everyday commands for building and running the cind container.

## Core targets

| Target | Description |
| --- | --- |
| `make help` | List all targets |
| `make env` | Refresh `.env`, runtime config, and project mounts from `cind.config.json` |
| `make path-check` | Show default project path and mounted projects |
| `make build` | Build the container image |
| `make rebuild` | Rebuild without cache |
| `make terminal` | Start browser terminal (no Docker socket) |
| `make terminal-docker` | Start browser terminal with host Docker socket |
| `make terminal-url` | Print browser terminal URL |
| `make down` | Stop containers |
| `make logs` | Follow container logs |
| `make validate` | Validate repository layout and scripts |
| `make test` | Run smoke tests |

## Starting the terminal

```bash
make terminal
# or with Docker-from-Docker:
make terminal-docker
```

`make terminal` prints the URL (default `http://localhost:7681`). Run `make terminal-url` to print it again.

### With a specific default project (no JSON config)

```bash
make terminal PROJECT_DIR=$HOME/projects/my-app
```

### With JSON config

```bash
make env CONFIG=./cind.config.json
make terminal-docker
```

## Compose stacks

| Target | Compose files |
| --- | --- |
| `make terminal` | `docker-compose.yml` + `.cind/compose-projects.generated.yml` + `docker-compose.ttyd.yml` |
| `make terminal-docker` | above + `docker-compose.docker.yml` |

Project paths come from `cind.config.json` → `.cind/compose-projects.generated.yml`.
Run `make env` after changing projects.

## Docker socket

`make terminal-docker` fails early if `/var/run/docker.sock` is absent.

Use it only when you need `docker compose` or `docker build` inside the container with host path parity.

## Other targets

| Target | Description |
| --- | --- |
| `make config` | Print resolved Compose config |
| `make init-project` | Bootstrap Cursor files in `PROJECT_DIR` |
| `make init-project-dry-run` | Preview bootstrap |
| `make clean` | Stop containers, keep volumes |
| `make clean-volumes` | Stop and delete named volumes (destructive) |
| `make docs` | Build documentation site |
| `make test-path-parity` | Integration test for path parity + Docker socket |

## Renamed targets (migration)

| Old | New |
| --- | --- |
| `make shell` | `make terminal` |
| `make shell-docker` | `make terminal-docker` |
| `make terminal` (URL only) | `make terminal-url` |
