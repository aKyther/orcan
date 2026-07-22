# Path parity

This page explains why the development container uses the **same absolute project path** on the host and inside the container.

## Why Compose worked on the host

When you run `docker compose` on the host, the CLI sends bind mount paths to the host Docker daemon.
Those paths exist on the host filesystem.
Relative mounts such as `.:/app` resolve against your current directory on the host.

## Why Compose failed inside the development container (old model)

Previously, the host project was mounted at a different path inside the container:

```text
Host project:     /home/user/projects/example
Container path:   /workspace
```

The container talks to the **host Docker daemon** through `/var/run/docker.sock`.
The daemon resolves bind mount **source paths on the host**, not inside the container.

When you ran `docker compose up` from `/workspace`, Compose sent `.:/app` meaning `/workspace` on the host — which does not exist on the host.
The mount failed or pointed at the wrong directory.

## What path parity means

The project uses one absolute path on both sides:

```text
Host:
  /home/user/projects/example

Development container:
  /home/user/projects/example

Docker daemon bind source:
  /home/user/projects/example
```

`PROJECT_DIR` in `.env` is that path.

## Why `/workspace` is not enough

`/workspace` existed only inside the development container.
The host Docker daemon never saw that path as your project root.
Path parity removes that mismatch.

## Configure the project

```bash
make setup PROJECT_DIR=/home/user/projects/example
make path-check
make terminal-docker
```

Inside the container:

```bash
pwd
echo "$PROJECT_DIR"
docker compose config
docker compose up
```

The path can differ between users and machines, but on one machine it must match between host and container.

## Container home vs project path

These are separate:

| Path | Role |
| --- | --- |
| `/home/developer` | Container user home (`${HOME}`) |
| `${PROJECT_DIR}` | Mounted project (same path as on the host) |
| `${HOME}/.cursor` | Global Cursor CLI config (named volume) |
| `${PROJECT_DIR}/.cursor` | Project-specific Cursor config |

## Validation

`make path-check` prints the effective paths and confirms parity is enabled.

Host-side validation (`scripts/repository/validate-project-dir.sh`) runs before `make terminal`, `make terminal-docker`, and `make build` via `require-generated.sh` (reads existing `.env` only — no regeneration).

It checks that `PROJECT_DIR`:

* is set and absolute,
* exists and is a readable directory,
* is not `/`, `/home`, or your entire home directory,
* does not contain `~`.

## Docker socket security

Path parity fixes Compose bind mounts.
It does **not** make Docker socket mode safe.

Mounting `/var/run/docker.sock` gives the container control over the host Docker Engine.
Use `make terminal-docker` only when you need it.
Use `make terminal` for the safer mode without the socket.

See [Security](security.md).

## Migration from `/workspace`

If you used the old `/workspace` mount:

1. Set `PROJECT_DIR` to the real absolute host path of your project.
2. Run `make env PROJECT_DIR=/absolute/path/to/project`.
3. Run `make path-check`.
4. Restart with `make down` then `make terminal` or `make terminal-docker`.
5. Inside the container, run commands from `${PROJECT_DIR}` (the shell and entrypoint do this automatically).

Update scripts or docs that hard-coded `/workspace`.
