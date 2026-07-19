# Makefile

The Makefile is the main user interface. Prefer it over raw `docker compose` commands.

## Command table

| Command | Description |
| --- | --- |
| `make help` | Show targets |
| `make env` | Create/update `.env` from the host |
| `make build` | Build the image |
| `make shell` | Interactive shell without Docker socket |
| `make shell-docker` | Interactive shell with Docker socket |
| `make up` | Foreground service without Docker socket |
| `make up-docker` | Foreground service with Docker socket |
| `make down` | Stop containers; keep volumes |
| `make logs` | Follow logs |
| `make rebuild` | Rebuild with `--no-cache` |
| `make clean` | Stop containers; keep named volumes |
| `make clean-volumes` | Delete named volumes after confirmation |
| `make config` | Validate base and docker-enabled Compose configs |
| `make init-project` | Create missing Cursor project files in `/workspace` |
| `make init-project-dry-run` | Dry-run project Cursor scaffolding |

## Examples

Refresh `.env` and open a project:

```bash
make env PROJECT_DIR=$HOME/projects/my-app
make shell PROJECT_DIR=$HOME/projects/my-app
```

Build once, then use Docker-from-Docker:

```bash
make build
make shell-docker PROJECT_DIR=$HOME/projects/my-app
```

Validate Compose without starting anything:

```bash
make config
```

Scaffold Cursor files in the mounted project:

```bash
make init-project-dry-run
make init-project
```

Reset caches after a broken toolchain state:

```bash
make clean-volumes
make rebuild
```

!!! warning

    `make clean-volumes` deletes Cursor config, bash history, and language caches.
    It asks you to type `yes` before it continues.

## How UID and socket detection work

On each `env` run the Makefile sets:

* `USER_UID` from `id -u`
* `USER_GID` from `id -g`
* `DOCKER_GID` from `stat` on `/var/run/docker.sock`, or `999` if the socket is missing

`shell-docker` and `up-docker` fail early if the socket file is absent.

## Compose invocation

| Target family | Files |
| --- | --- |
| Default | `docker-compose.yml` |
| `*-docker` | `docker-compose.yml` + `docker-compose.docker.yml` |
