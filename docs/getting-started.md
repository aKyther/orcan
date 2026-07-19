# Getting started

This page walks through the first run from an empty clone to a working shell.

## 1. Clone the repository

```bash
git clone <repository-url> cursor-cli-devcontainer
cd cursor-cli-devcontainer
```

## 2. Create your local `.env`

```bash
cp .env.example .env
make env
```

`make env` fills:

* `USER_UID` / `USER_GID` from your host account
* `DOCKER_GID` from `/var/run/docker.sock` when present
* `PROJECT_DIR` (defaults to this repository path)

## 3. Build the image

```bash
make build
```

The first build downloads base images and tool stages. Later builds are faster because of Docker layer and BuildKit caches.

## 4. Open a shell in your project

```bash
make shell PROJECT_DIR=$HOME/projects/my-app
```

Replace `$HOME/projects/my-app` with the absolute path of the project you want Cursor to edit.

!!! note

    The default `make shell` does **not** mount the Docker socket.
    Use `make shell-docker` only when you need Docker-from-Docker.

## 5. Confirm tools

Inside the container:

```bash
agent --version
test -d "${HOME}/.cursor"
cursor-init-project --help
```

## 6. Optional: scaffold Cursor files in the mounted project

```bash
cursor-init-project --dry-run
cursor-init-project
```

Review the files before you commit them.

## 7. Use TMUX

Interactive shells start TMUX automatically (session name: `cursor`).
Config comes from the repo file `.tmux.conf` (prefix: `Ctrl-Space`).

| Action | Keys |
| --- | --- |
| Detach | `Ctrl-Space` `d` |
| Reattach | `tmux attach -t cursor` |
| New window | `Alt-c` |

## Next steps

* Read [Docker](docker.md) to understand mounts and volumes
* Read [Security](security.md) before enabling the Docker socket
* Read [Cursor](cursor.md) for agent rules and ignore files
