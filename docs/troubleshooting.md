# Troubleshooting

## UID/GID conflicts or permission denied in `/workspace`

**Symptom:** cannot write files, or files appear as another user on the host.

**Fix:**

```bash
make env
make build
make shell PROJECT_DIR=/absolute/path/to/project
```

Confirm `.env` has your real host IDs:

```bash
id -u
id -g
grep USER_ /.env
```

## Cannot access Docker socket

**Symptom:** `permission denied while trying to connect to the Docker daemon socket`, or `no such file or directory` for `/var/run/docker.sock` inside the container.

**Fix:**

1. Confirm the socket exists on the host: `ls -l /var/run/docker.sock`
2. Refresh group id: `make env`
3. Use the docker-enabled target: `make shell-docker` (not `make shell`)
4. If you previously ran `make shell`, run `make shell-docker` again — it stops the SSH-only container and recreates with the socket.

Inside the container, check:

```bash
id
ls -l /var/run/docker.sock
docker ps
```

You should see group `docker` (or your host `DOCKER_GID`) and the socket file present.

## Cursor login fails with `EPERM` on `~/.config/cursor`

**Symptom:** `Failed to store authentication tokens: EPERM: operation not permitted, chmod '/home/developer/.config/cursor'`.

**Cause:** the `cursor-app-config` named volume was created with `root` ownership (common on first mount).

**Fix:**

Restart the container so the entrypoint can repair ownership:

```bash
make down
make shell-docker   # or make shell
```

If login still fails:

```bash
make clean-volumes
make shell-docker
```

Then log in again inside the container.

## No TTY / broken interactive session

**Symptom:** TMUX or Cursor CLI behave oddly; Compose warns about TTY.

**Fix:**

* Run from a real terminal, not a non-interactive pipe
* Connect over SSH after `make shell` (`ssh developer@localhost`)
* TMUX starts automatically inside the SSH session

## TMUX did not start

**Checks:**

* Are you in an interactive terminal? (`[ -t 0 ]` must be true)
* Is `TMUX` already set?
* Is `tmux` on `PATH`?

Manual start:

```bash
tmux new-session -A -s cursor
```

## Stale image or missing new tools

```bash
make rebuild
```

If caches look corrupt:

```bash
make clean-volumes
make rebuild
```

## Cursor CLI not logged in

Run the login flow inside the container once. Auth persists in the `cursor-app-config` volume (`~/.config/cursor/auth.json`) across restarts.

If login state is broken:

```bash
make clean-volumes
make shell
ssh developer@localhost
```

Then log in again.

## Compose config errors

```bash
make config
```

Common causes:

* invalid `.env` values
* missing `PROJECT_DIR`
* edited YAML indentation

## `make shell-docker` fails immediately

The Makefile exits if `/var/run/docker.sock` is missing. Start Docker Engine/Desktop, then retry.

## Cannot bind SSH port 22

The host may already run `sshd` on port 22. Set another port in `.env`:

```bash
SSH_HOST_PORT=2222
```

Then:

```bash
make shell
ssh -p 2222 developer@localhost
```

## Useful diagnostic commands

```bash
make help
make config
docker compose -f docker-compose.yml config
docker compose -f docker-compose.yml -f docker-compose.docker.yml config
docker compose -f docker-compose.yml -f docker-compose.ssh.yml config
docker images | grep cursor-dev
```
