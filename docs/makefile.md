# Makefile

The Makefile is the main user interface. Prefer it over raw `docker compose` commands.

Complex host logic lives in `scripts/repository/`. The Makefile stays thin.

## Command table

| Command | Description |
| --- | --- |
| `make help` | Show targets |
| `make env` | Create/update `.env` from the host |
| `make build` | Build the image |
| `make rebuild` | Rebuild with `--no-cache` |
| `make shell` | Interactive shell without Docker socket |
| `make shell-docker` | Interactive shell with Docker socket |
| `make up` | Foreground service without Docker socket |
| `make up-docker` | Foreground service with Docker socket |
| `make up-ssh` | Detached OpenSSH daemon without Docker socket |
| `make up-ssh-docker` | Detached OpenSSH daemon with Docker socket |
| `make down` | Stop containers; keep volumes |
| `make logs` | Follow logs |
| `make clean` | Stop containers; keep named volumes |
| `make clean-volumes` | Delete named volumes after confirmation |
| `make config` | Validate base and docker-enabled Compose configs |
| `make init-project` | Create missing Cursor project files in `/workspace` |
| `make init-project-dry-run` | Dry-run project Cursor scaffolding |
| `make validate` | Check layout, script syntax, Compose config |
| `make test` | Run container smoke tests |
| `make docs` | Build MkDocs site |
| `make docs-serve` | Serve MkDocs locally |

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

Validate the repository and Compose files:

```bash
make validate
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

`make env` calls `scripts/repository/update-env.sh`, which sets:

* `USER_UID` from `id -u`
* `USER_GID` from `id -g`
* `DOCKER_GID` from `stat` on `/var/run/docker.sock`, or `999` if the socket is missing

`shell-docker` and `up-docker` fail early if the socket file is absent.

## Compose invocation

| Target family | Files |
| --- | --- |
| Default | `docker-compose.yml` |
| `*-docker` | `docker-compose.yml` + `docker-compose.docker.yml` |
| `up-ssh` | `docker-compose.yml` + `docker-compose.ssh.yml` |
| `up-ssh-docker` | `docker-compose.yml` + `docker-compose.ssh.yml` + `docker-compose.docker.yml` |

SSH on a VPS (Tailscale):

```bash
make build
make up-ssh PROJECT_DIR=/absolute/path/to/project
ssh developer@<tailscale-ip>
```

Default password is `cursor` (`DEVELOPER_PASSWORD`). Change it in `.env` before production use.
