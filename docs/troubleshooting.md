# Troubleshooting

## Invalid or missing `PROJECT_DIR`

**Symptom:** `make terminal` or `make build` fails with a `PROJECT_DIR` validation error.

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
make terminal PROJECT_DIR=/absolute/path/to/project
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
3. Use the docker-enabled target: `make terminal-docker` (not `make terminal`)
4. If you previously ran `make terminal`, run `make terminal-docker` again — it stops the ttyd-only container and recreates with the socket.

Inside the container, check:

```bash
id
ls -l /var/run/docker.sock
docker ps
```

You should see group `docker` (or your host `DOCKER_GID`) and the socket file present.

## Cursor login fails with `EPERM` on `~/.config/cursor`

**Symptom:** `Failed to store authentication tokens: EPERM: operation not permitted, chmod '/home/developer/.config/cursor'`.

**Cause:** `$CIND_DATA/cursor-app` on the host is owned by root (or wrong UID).

**Fix:**

```bash
make env                 # recreates dirs and chowns to USER_UID/USER_GID
make down
make terminal-docker
```

If login still fails:

```bash
make clean-data
make env
make terminal-docker
```

Then log in again inside the browser terminal.

## No TTY / broken interactive session

**Symptom:** TMUX or Cursor CLI behave oddly; Compose warns about TTY.

**Fix:**

* Open the browser terminal at `http://localhost:7681` after `make terminal`
* TMUX starts automatically inside the ttyd session (session name: `workspace`)
* Run `make terminal` if you forgot the URL

## tmux keys do not work in the browser

**Symptom:** `Alt+c`, `Ctrl+arrow`, or your usual tmux splits do nothing in ttyd.

**Cause:**

1. cind tmux is **`/etc/tmux/`** (aligned with typical `~/.tmux.conf`) — not your host file unless you copy binds into the container.
2. Browsers often capture **`Alt+*`** and **`Ctrl+arrow`** before ttyd receives them (bindings exist but never arrive).

**Fix — try in order:**

1. Click inside the terminal.
2. Mouse is on by default; **`Alt+q`** disables it if needed.
3. Prefix: **`Ctrl+Space`** then **`-`** or **`|`**.
4. On desktop browser where keys do get through: **`Ctrl+arrow`** splits, **`Alt+arrow`** moves panes (same as local tmux).

**After image tmux changes:** `make rebuild`, new tmux session, or `Ctrl+Space` `r` inside tmux.

## Legacy: host `~/.gitconfig` became a directory

**Symptom:** on the host, `~/.gitconfig` is a **directory** (often root-owned) after an older cind version.

**Cause:** Docker bind-mounted a missing `~/.gitconfig` file and created a directory.

**Fix:** remove it on the host (cind no longer mounts gitconfig):

```bash
sudo rm -rf ~/.gitconfig
```

Configure Git inside the container when you need it — identity is not shared with the host.

## `/etc/tmux/options.conf: invalid environment variable`

**Symptom:** ttyd opens but tmux fails immediately with `invalid environment variable` on line 3 of `options.conf`. You may need to click or refresh several times before a session appears.

**Cause:** tmux config does not support bash-style defaults such as `${SHELL:-/bin/bash}`.

**Fix:** rebuild the image so the fixed config is baked in:

```bash
make rebuild
make down
make terminal-docker   # or make terminal
```

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

`make rebuild` only needs `.env` (for `USER_UID` / `USER_GID` build args). It does **not** re-run `make env`.

### `make rebuild` fails during pnpm / Node step

**Symptom:** `corepack prepare pnpm@latest` or `npm install -g pnpm` fails with `TypeError: terminated` or network errors.

**Cause:** flaky download from npm/corepack on VPS.

**Fix:** pull latest cind — pnpm is installed from a pinned GitHub release binary with retries. Then:

```bash
make rebuild
```

### `make rebuild` fails before Docker starts

**Symptom:** `Error: .env is missing` or `generated runtime files are missing`.

**Fix:**

```bash
make env
make rebuild
```

For image-only rebuilds, `.env` is enough. Generated mounts are required for `make terminal*`, not for `make rebuild`.

### Wrong workspace name vs mounts (or only one of two workspaces)

**Symptom:** after adding a second workspace, the launcher shows the new name but the directory/mounts look like the previous workspace — or only one session appears.

**Cause:** `cind.config.json` was edited without regenerating mounts and recreating the container. The runtime JSON is bind-mounted (names update live); Docker bind mounts do not (need recreate).

**Fix:**

```bash
make env
make down && make terminal-docker
```

Then pick the workspace by number in the launcher. Confirm with `make config-show`.

### Out of disk during `--no-cache`

**Symptom:** build fails mid-way with `no space left on device`.

**Fix:** `docker system df`, prune unused images, then retry `make rebuild`. Full no-cache rebuild needs several GB free.

If caches look corrupt:

```bash
make clean-data
make env
make rebuild
```

## Cursor CLI not logged in

Run the login flow inside the browser terminal once. Auth persists in `$CIND_DATA/cursor-app` (`~/.config/cursor/auth.json` in the container) across restarts.

If login state is broken:

```bash
make clean-data
make env
make terminal
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

## `make terminal-docker` fails immediately

The Makefile exits if `/var/run/docker.sock` is missing. Start Docker Engine/Desktop, then retry.

## Cannot bind ttyd port 7681

Another process may already use port `7681` on the host. Set another port in `.env`:

```bash
TTYD_HOST_PORT=8765
```

Then:

```bash
make terminal
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
docker images | grep cind
```
