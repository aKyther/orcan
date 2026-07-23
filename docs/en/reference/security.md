# Security

## Isolation limits

Orcan is convenient isolation, **not** a hard security boundary.

- Bind mounts give the container write access to your projects
- `make terminal-docker` mounts `/var/run/docker.sock` → strong host access

!!! warning
    Use `terminal-docker` only when you need Docker-from-Docker. Prefer `make terminal` when you do not.

## Data on the host

Logins and caches live under `$ORCAN_DATA` (default `~/.config/orcan`). Treat that directory as sensitive.

`make clean-data` deletes it after confirmation.

## Browser terminal

!!! warning
    ttyd has **no authentication** in the default setup. Bind to localhost, or put it behind Tailscale / a VPN. Do not expose the port to the public Internet without auth and TLS.

## What not to do

- Do not start `--privileged` containers for Orcan
- Do not mount `/`, `/home`, or `/etc` as `PROJECT_DIR`
- Do not commit `.env`, tokens, or `ORCAN_DATA` contents
- Do not run `docker system prune` as part of normal Orcan workflows
