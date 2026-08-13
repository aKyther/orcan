# Security

## Isolation limits

Orcan is convenient isolation, **not** a hard security boundary.

- Bind mounts give the container write access to your projects
- `orcan up --with-docker` mounts `/var/run/docker.sock` → strong host access
- `orcan up --with-git` mounts host `~/.ssh` (read-only) and may mount the SSH agent socket
- `orcan up --with-network NAME` joins an existing Docker network → network-level reachability to whatever else is on it, but no socket and no host control

!!! warning
    Use `orcan up --with-docker` only when you need Docker-from-Docker. Prefer plain `orcan up` when you do not need the socket.

!!! warning
    Use `orcan up --with-git` only when you need push/pull from inside the container. It exposes your SSH keys (and agent) to the container.

If you only need the container to reach another container by name/IP,
`orcan up --with-network NAME` is the safer choice — it does not grant
control over the host Docker engine the way `--with-docker` does.

## Data on the host

Logins and caches live under `$ORCAN_DATA` (default `~/.config/orcan`). Treat that directory as sensitive.

`orcan uninstall --purge-data` deletes it after confirmation.

## Browser terminal

!!! warning
    ttyd has **no authentication** in the default setup. Bind to localhost, or put it behind Tailscale / a VPN. Do not expose the port to the public Internet without auth and TLS.

## What not to do

- Do not start `--privileged` containers for Orcan
- Do not mount `/`, `/home`, or `/etc` as `PROJECT_DIR`
- Do not commit `.env`, tokens, or `ORCAN_DATA` contents
- Do not run `docker system prune` as part of normal Orcan workflows
