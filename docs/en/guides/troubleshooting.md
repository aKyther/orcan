# Troubleshooting

## What this does

Lists common failures and how to diagnose them on the **host**.

## Before you start

From the Orcan repo:

```bash
make validate
make path-check
make config
```

`make config` prints the resolved Compose file (needs generated `.orcan` files).

## Browser terminal will not open

1. Confirm the container is up: `make logs`
2. Confirm the URL: `make terminal-url` (default `http://localhost:7681`)
3. If the port is busy, change `ttyd.host_port` in `orcan.config.json`, then `make env` and recreate

## Launcher is empty / wrong projects

1. Check `orcan.config.json` has `workspaces` with absolute `projects[].path`
2. Run `make env` (terminal targets do not refresh config)
3. `make down && make terminal-docker`

Do **not** pass `PROJECT_DIR=…` on `make terminal`. Switch projects by editing config + `make env`.

## `make env` / `require-generated` fails

| Message | Fix |
| --- | --- |
| `.env` missing | `make env` or `make setup` |
| Generated files stale | Config is newer than `.orcan/*` — run `make env` |
| Invalid `PROJECT_DIR` | Absolute path; avoid `/`, `/home`, `/etc` |

## Agent or Claude missing

- Full image: `make build` then recreate container
- Claude-only: `IMAGE_LOCAL=orcan:claude` — `agent` is not installed (expected)
- Auth lives under `$ORCAN_DATA` (`~/.config/orcan`)

## Docker socket errors inside the container

Use `make terminal-docker`. Plain `make terminal` does not mount the socket.

## Path parity / nested Compose fails

See [Path parity](../concepts/path-parity.md). Confirm mounts with `make path-check`.

## tmux keys do not work in the browser

Focus the terminal pane. Use tmux prefix (see image defaults under `/etc/tmux`). Right-click uses the browser menu (tmux mouse menus are unbound on purpose).

## “Disable tmux” / plain shell only

tmux is started by the launcher (`cursor-ttyd` → `cursor-launcher`), not by a block in `50-orcan-shell.zsh`. There is no supported “turn off tmux” switch today. You can still open extra shells inside tmux windows.

## Host `~/.gitconfig` became a directory

An older layout could create a root-owned directory. Fix ownership or replace with a normal file, then update Orcan and recreate the container.

## Diagnostics checklist

```bash
make validate
make path-check
docker compose -f docker-compose.yml -f .orcan/compose-projects.generated.yml config
make logs
```

More on limits: [Security](../reference/security.md).
