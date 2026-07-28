# Troubleshooting

## What this does

Lists common failures and how to diagnose them on the **host**.

## Before you start

From the Orcan install (or git checkout):

```bash
orcan doctor
orcan context show
docker compose -f docker-compose.yml -f .orcan/compose-projects.generated.yml config
```

The `docker compose config` command prints the resolved Compose file (needs generated `.orcan` files from `orcan sync`).

## Browser terminal will not open

1. Confirm the container is up: `orcan logs`
2. Confirm the URL: `orcan url` (default `http://localhost:7681`)
3. If the port is busy, change `ttyd.host_port` in `orcan.config.json`, then `orcan sync` and recreate

## Launcher is empty / wrong projects

1. Check `orcan.config.json` has `workspaces` with absolute `projects[].path`
2. Run `orcan sync` (terminal targets do not refresh config)
3. `orcan down && orcan up`

Do **not** pass `PROJECT_DIR=…` on `orcan up`. Switch projects by editing config + `orcan sync`.

## `orcan sync` / `require-generated` fails

| Message | Fix |
| --- | --- |
| `.env` missing | `orcan sync` or `orcan init` |
| Generated files stale | Config is newer than `.orcan/*` — run `orcan sync` |
| Invalid `PROJECT_DIR` | Absolute path; avoid `/`, `/home`, `/etc` |

## Agent or Claude missing

- Full image: `orcan build` then recreate container
- Claude-only: `orcan build --claude` then `IMAGE_LOCAL=orcan:<VERSION>-claude orcan up` — `agent` is not installed (expected)
- Auth lives under `$ORCAN_DATA` (`~/.config/orcan`)

## Docker socket errors inside the container

Use `orcan up --with-docker`. Plain `orcan up` does not mount the socket.

If `docker` needs `sudo` inside the container, the host socket GID must match `DOCKER_GID` in `.env`:

```bash
stat -c '%g' /var/run/docker.sock
grep DOCKER_GID "${ORCAN_HOME:-$HOME/.config/orcan/home}/.env"
orcan sync && orcan down && orcan up --with-docker
```

`orcan sync` re-detects the socket GID from the host (do not leave a stale `999` from `.env.example`).

## Path parity / nested Compose fails

See [Path parity](../concepts/path-parity.md). Confirm mounts with `orcan context show`.

## tmux keys do not work in the browser

Focus the terminal pane. Use tmux prefix (see image defaults under `/etc/tmux`). Right-click uses the browser menu (tmux mouse menus are unbound on purpose).

## Long URL wraps and is hard to click

Browser/terminal linkify usually matches **one screen row**. Soft-wrapped `https://…` links break into pieces, so click-to-open fails.

Workaround (image default): **prefix `u`** (`C-Space` then `u`) — joins wrapped lines in the pane, then copies the URL (menu if several). Paste with prefix `]` or the browser paste shortcut.

Apps that emit OSC 8 hyperlinks can stay clickable across wraps when the outer terminal supports them; plain printed URLs still need prefix `u`.

## “Disable tmux” / plain shell only

tmux is started by the launcher (`cursor-ttyd` → `agent-launcher`), not by a block in `50-orcan-shell.zsh`. There is no supported “turn off tmux” switch today. You can still open extra shells inside tmux windows.

## Host `~/.gitconfig` became a directory

An older layout could create a root-owned directory. Fix ownership or replace with a normal file, then update Orcan and recreate the container.

Orcan does **not** mount host `~/.gitconfig`. Instead `orcan sync` copies `user.name` / `user.email` into `.env` (`GIT_AUTHOR_*` / `GIT_COMMITTER_*`) so commits inside the container match the host author.

For `git push` / `git pull` over SSH:

```bash
orcan up --with-git
# combine with DinD:
orcan up --with-docker --with-git
```

That mounts host `~/.ssh` read-only (and the SSH agent when `SSH_AUTH_SOCK` is set). Plain `orcan up` does not.

## Diagnostics checklist

```bash
orcan doctor
orcan context show
docker compose -f docker-compose.yml -f .orcan/compose-projects.generated.yml config
orcan logs
```

More on limits: [Security](../reference/security.md).
