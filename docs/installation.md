# Installation

## Requirements

| Requirement | Why |
| --- | --- |
| Docker Engine or Docker Desktop | Runs the container |
| Docker Compose v2 (`docker compose`) | Reads Compose files |
| GNU Make | Runs the project commands |
| Linux or compatible environment (WSL2 works) | UID/GID and socket paths match the Makefile |
| Host Docker socket | Only for `*-docker` targets |

Check versions:

```bash
docker version
docker compose version
make --version
```

## Clone

```bash
git clone <repository-url> cursor-cli-devcontainer
cd cursor-cli-devcontainer
```

## Configure environment

```bash
cp .env.example .env
make env
```

Example `.env` values:

```dotenv
USER_UID=1000
USER_GID=1000
DOCKER_GID=999
PROJECT_DIR=/absolute/path/to/project
CPUS=8
MEMORY=16g
SHM_SIZE=2g
TMPFS_SIZE=2g
```

!!! warning

    Do not put tokens, passwords, or private keys in `.env`.
    `.env` is gitignored.

## Build

```bash
make build
```

## Run

Without Docker socket:

```bash
make shell PROJECT_DIR=/absolute/path/to/project
ssh developer@localhost
```

With Docker socket:

```bash
make shell-docker PROJECT_DIR=/absolute/path/to/project
ssh developer@localhost
```

## Optional: documentation site

```bash
pip install mkdocs-material
mkdocs serve
```

Open the URL printed by MkDocs (usually `http://127.0.0.1:8000`).
