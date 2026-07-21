# Troubleshooting

## Invalid or missing `PROJECT_DIR`

**Symptom:** `make shell` or `make build` fails with a `PROJECT_DIR` validation error.

**Fix:**

1. Set an absolute path in `.env` (no `.`, `../`, or `~`).
2. Run `make env PROJECT_DIR=/absolute/path/to/project`.
3. Run `make path-check`.

See [Path parity](path-parity.md).

## UID/GID conflicts or permission denied in `PROJECT_DIR`

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
4. If you previously ran `make shell`, run `make shell-docker` again — it stops the ttyd-only container and recreates with the socket.

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

Then log in again inside the browser terminal.

## No TTY / broken interactive session

**Symptom:** TMUX or Cursor CLI behave oddly; Compose warns about TTY.

**Fix:**

* Open the browser terminal at `http://localhost:7681` after `make shell`
* TMUX starts automatically inside the ttyd session (session name: `workspace`)
* Run `make terminal` if you forgot the URL

## TMUX did not start

**Checks:**

* Did you open the browser terminal URL (not a raw `docker exec`)?
* Is the container healthy? (`docker compose ps`)
* Is `tmux` on `PATH`?

Manual start (inside the container):

```bash
tmux new-session -A -s workspace
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

Run the login flow inside the browser terminal once. Auth persists in the `cursor-app-config` volume (`~/.config/cursor/auth.json`) across restarts.

If login state is broken:

```bash
make clean-volumes
make shell
```

Open `http://localhost:7681` and log in again.

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

## Cannot bind ttyd port 7681

Another process may already use port `7681` on the host. Set another port in `.env`:

```bash
TTYD_HOST_PORT=8765
```

Then:

```bash
make shell
```

Open `http://localhost:8765` (or run `make terminal`).

## Useful diagnostic commands

```bash
make help
make terminal
make config
docker compose -f docker-compose.yml config
docker compose -f docker-compose.yml -f docker-compose.docker.yml config
docker compose -f docker-compose.yml -f docker-compose.ttyd.yml config
docker images | grep cursor-dev
```
