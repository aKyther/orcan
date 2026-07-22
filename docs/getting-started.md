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
* `PROJECT_DIR` (absolute path; defaults to this repository path when you run `make env`)

!!! tip

    Use an absolute path only — not `.`, `../`, or `~/project`. See [Path parity](path-parity.md).

## 3. Check path parity

```bash
make path-check
```

## 4. Build the image

```bash
make build
```

The first build downloads base images and tool stages. Later builds are faster because of Docker layer and BuildKit caches.

## 5. Start the container and open the browser terminal

```bash
make env PROJECT_DIR=$HOME/projects/my-app
make path-check
make terminal
```

Replace `$HOME/projects/my-app` with the absolute path of the project you want Cursor to edit.

Open the URL printed by `make terminal` (default: `http://localhost:7681`).

!!! note

    `make terminal` does **not** mount the Docker socket.
    Use `make terminal-docker` only when you need Docker-from-Docker.

!!! warning

    ttyd has no authentication. Use only on localhost or a private network (Tailscale).

## 6. Confirm tools

In the browser terminal:

```bash
agent --version
test -d "${HOME}/.cursor"
cursor-init-project --help
```

## 7. Optional: scaffold Cursor files in the mounted project

```bash
cursor-init-project --dry-run
cursor-init-project
```

Review the files before you commit them.

## 8. Use TMUX

The browser terminal starts TMUX automatically (session name: `workspace`).
Config comes from `docker/rootfs/etc/skel/.tmux.conf` (prefix: `Ctrl-Space`).

| Action | Keys |
| --- | --- |
| Detach | `Ctrl-Space` `d` |
| Reattach | `tmux attach -t workspace` |
| New window | `Alt-c` |

## Next steps

* Read [Path parity](path-parity.md) before using `docker compose` inside the container
* Read [Docker](docker.md) to understand mounts and volumes
* Read [Security](security.md) before enabling the Docker socket
* Read [Cursor](cursor.md) for agent rules, image defaults, and ignore files
* Read [Development](development.md) for repository vs container file layout
