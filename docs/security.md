# Security

This page is intentionally direct. Containers help, but they are not a full security boundary for every setup.

## What is isolated

* Host package installs are not required for the toolchain
* Language tools live in the image
* Caches and Cursor config live in named volumes
* Base Compose does not mount the Docker socket

## What is not isolated

* The bind-mounted project is writable on the host
* Read-only `~/.ssh` and `~/.gitconfig` share host identity with the container
* `sudo` inside the container is root in the container
* Docker socket mode can control the host Docker Engine

## Docker socket

!!! warning

    `/var/run/docker.sock` is privileged host access.
    A process that can talk to the socket can start containers, mount host paths, and often reach host data.

Use socket mode only when needed:

```bash
make shell-docker
```

Default mode:

```bash
make shell
```

## Bind mounts

| Mount | Risk |
| --- | --- |
| `PROJECT_DIR -> /workspace` | Agent can edit that project on the host |
| `~/.ssh` (read-only) | Private keys are visible inside the container |
| `~/.gitconfig` (read-only) | Git identity is shared |

Do **not** mount:

* `/`
* `/home`
* `/etc`
* unrelated disks or backup trees

## Volumes

Named volumes persist data after containers stop. That is useful for caches and login state. It also means secrets written into those paths can survive `make down`.

Delete them only with:

```bash
make clean-volumes
```

## Secrets

* Keep `.env` out of git (already gitignored)
* Do not bake tokens into the Dockerfile
* Do not copy SSH keys into the image layers
* Prefer environment injection or short-lived credentials when possible
* Do not mount the host `~/.cursor` directory into the container

## Agent rules vs isolation

Text rules in `${HOME}/.cursor/rules` and project `.cursor/rules` guide the agent.
They do **not** replace Docker isolation or OS permissions.

## SSH keys

The base Compose file mounts `~/.ssh` read-only for Git over SSH.

Safer long-term option (see [Development — Roadmap](development.md#roadmap)): SSH agent forwarding instead of mounting the whole `.ssh` directory.

## SSH server (always on)

`make shell` and `make shell-docker` start `sshd` inside the container.

* Default user: `developer`
* Default password: `cursor` (`DEVELOPER_PASSWORD`)
* Default host port: `22` (`SSH_HOST_PORT`)
* Does not mount host `~/.ssh` or `~/.gitconfig`

!!! warning

    Password login is intentional for a simple Tailscale setup. Do not expose this port on the public internet.
    Prefer Tailscale (or another private network). Change `DEVELOPER_PASSWORD` in `.env`.

```bash
make shell
ssh developer@localhost
```

On a VPS, use the machine's Tailscale IP instead of `localhost`.

## Permissions

Matching `USER_UID` / `USER_GID` avoids root-owned files in your project. It does not replace access control on the host.

## Good practices

1. Use `make shell` by default.
2. Mount the smallest project directory that works.
3. Keep production secrets off developer laptops when you can.
4. Review `.cursorignore` when you add credential paths.
5. Do not run `--privileged` containers from this project.
6. Do not use `docker system prune` from an agent session unless you mean it.
