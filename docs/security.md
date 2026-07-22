# Security

This page is intentionally direct. Containers help, but they are not a full security boundary for every setup.

## What is isolated

* Host package installs are not required for the toolchain
* Language tools live in the image
* Caches and Cursor config live in named volumes
* Base Compose does not mount the Docker socket
* **No SSH server** — shell access is browser-only (ttyd + tmux)

## What is not isolated

* The bind-mounted project is writable on the host
* Read-only `~/.gitconfig` (when present on the host) shares Git identity with the container
* `sudo` inside the container is root in the container
* Docker socket mode can control the host Docker Engine

## Remote access (Tailscale)

There is **no SSH** into cind. The supported remote path is:

```text
Tailscale (or localhost) → http://<host>:7681 → workspace picker → tmux
```

1. Install [Tailscale](https://tailscale.com/) on the host (or use localhost only).
2. Run `make terminal` or `make terminal-docker`.
3. Open `http://<tailscale-ip>:7681` from a device on the same tailnet.

!!! warning

    ttyd has **no authentication**. Anyone who can reach port `7681` gets a shell as the `developer` user.
    **Do not** port-forward `7681` to the public Internet without auth and TLS.
    Tailscale provides network-layer access control — keep the tailnet trusted.

Use Git over **HTTPS** inside the container (no host `~/.ssh` mount, no `openssh-client` in the image).

## Docker socket

!!! warning

    `/var/run/docker.sock` is privileged host access.
    A process that can talk to the socket can start containers, mount host paths, and often reach host data.

Use socket mode only when needed:

```bash
make terminal-docker
```

Default mode:

```bash
make terminal
```

## Bind mounts

| Mount | Risk |
| --- | --- |
| Project paths (path parity) | Agent can edit those repos on the host |
| `~/.gitconfig` (read-only, optional) | Git identity is shared |

Do **not** mount:

* `/`
* `/home`
* `/etc`
* `~/.ssh` or other credential directories
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
* Do not mount SSH keys or the host `~/.cursor` directory into the container
* Prefer environment injection or short-lived credentials when possible

## Agent rules vs isolation

Text rules in `${HOME}/.cursor/rules` and project `.cursor/rules` guide the agent.
They do **not** replace Docker isolation or OS permissions.

## Browser terminal (ttyd + tmux)

`make terminal` and `make terminal-docker` start ttyd inside the container.

* Default URL: `http://localhost:7681`
* Host port: `7681` (`TTYD_HOST_PORT`)
* Flow: browser → workspace picker → one tmux session per workspace

```bash
make terminal-docker
```

Open `http://localhost:7681` locally, or `http://<tailscale-ip>:7681` on a remote host in your tailnet.

## Permissions

Matching `USER_UID` / `USER_GID` avoids root-owned files in your project. It does not replace access control on the host.

## Good practices

1. Use `make terminal` by default; add Tailscale for remote access instead of SSH.
2. Mount the smallest project directories that work.
3. Keep production secrets off developer laptops when you can.
4. Review `.cursorignore` when you add credential paths.
5. Do not run `--privileged` containers from this project.
6. Do not use `docker system prune` from an agent session unless you mean it.
