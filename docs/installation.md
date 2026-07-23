# Installation

## Requirements

| Requirement | Why |
| --- | --- |
| Docker Engine or Docker Desktop | Runs the container |
| Docker Compose v2 (`docker compose`) | Reads Compose files |
| GNU Make | Runs the project commands |
| Linux or compatible environment (WSL2 works) | UID/GID and socket paths match the Makefile |
| Host Docker socket | Only for `*-docker` targets |
| Web browser | Opens the ttyd terminal at `http://localhost:7681` |

Check versions:

```bash
docker version
docker compose version
make --version
```

## Clone

```bash
git clone <repository-url> orcan
cd orcan
```

## Configure environment

```bash
make config-wizard
make env
make build
make terminal-docker
```

Or with `setup` (scaffolds a one-project config if missing):

```bash
make setup PROJECT_DIR=/absolute/path/to/your/project
make build
make terminal-docker
```

`make setup` / `make env` create `.env` automatically when missing (from `.env.example` + host UID/GID).
After any later config change: `make env`, then `make down && make terminal-docker`.

Example `.env` values:

```dotenv
USER_UID=1000
USER_GID=1000
DOCKER_GID=999
PROJECT_DIR=/absolute/path/to/your/project
CPUS=8
MEMORY=16g
SHM_SIZE=2g
TMPFS_SIZE=2g
TTYD_PORT=7681
TTYD_HOST_PORT=7681
```

!!! warning

    Do not put tokens, passwords, or private keys in `.env`.
    `.env` is gitignored.

!!! note

    `PROJECT_DIR` must be an absolute path. Compose does not expand `~` reliably.
    Run `make path-check` after `make env`.

## Build

```bash
make build
```

## Run

Without Docker socket:

```bash
make env PROJECT_DIR=/absolute/path/to/project
make path-check
make terminal
```

Open `http://localhost:7681` in your browser (or run `make terminal`).

With Docker socket:

```bash
make terminal-docker
```

Then open the URL printed by the Makefile (default `http://localhost:7681`).

## Optional: documentation site

```bash
pip install mkdocs-material
mkdocs serve
```

Open the URL printed by MkDocs (usually `http://127.0.0.1:8000`).
