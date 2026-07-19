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

**Symptom:** `permission denied while trying to connect to the Docker daemon socket`.

**Fix:**

1. Confirm the socket exists: `ls -l /var/run/docker.sock`
2. Refresh group id: `make env`
3. Use the docker-enabled target: `make shell-docker`

## No TTY / broken interactive session

**Symptom:** TMUX or Cursor CLI behave oddly; Compose warns about TTY.

**Fix:**

* Run from a real terminal, not a non-interactive pipe
* Keep `stdin_open: true` and `tty: true` in Compose
* Prefer `make shell` over detached workflows when you need a TTY

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

Run the login flow inside the container. Config persists in the `cursor-config` volume across restarts.

If login state is broken:

```bash
make clean-volumes
make shell
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
make up-ssh
ssh -p 2222 developer@<tailscale-ip>
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
