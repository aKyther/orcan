# Troubleshooting

## What this does

Lists common failures and how to diagnose them on the **host**.

## Before you start

From the Orcan install (or git checkout):

```bash
orcan doctor
orcan context show
docker compose -f docker-compose.yml -f mounts/compose-projects.generated.yml config
```

The `docker compose config` command prints the resolved Compose file (needs generated `mounts/` files from `orcan sync`).

## Browser terminal will not open

Requires `orcan up --with-ttyd` (plain `orcan up` is local-only — use `orcan enter` instead).

1. Confirm the container is up: `orcan logs`
2. Confirm ttyd is on: `orcan doctor` (Runtime section) or `orcan url`
3. Confirm the URL: `orcan url` (prints `http://localhost:7681` when `TTYD_BIND` is `0.0.0.0`)
4. If the port is busy, change `ttyd.host_port` in `orcan.config.json`, then `orcan sync` and `orcan down && orcan up --with-ttyd`

## Frequent “reconnecting” on phone / mobile network

Cellular handoffs drop the ttyd WebSocket; that is expected. Processes inside tmux survive.

- After reconnect, `agent-launcher` auto-reattaches to the last workspace (Enter during the countdown → menu).
- Disable auto-reattach: `ORCAN_AUTO_REATTACH=0` on the container.
- Prefer Tailscale / VPN over exposing the port; still expect brief reconnects on LTE.
- Optional: `ttyd.ping_interval` / `TTYD_PING_INTERVAL` (default `20`).

## Layout glitches when the on-screen keyboard opens (phone / tablet)

Known upstream ttyd limitation, not an orcan config issue: ttyd's bundled
xterm.js frontend doesn't sync the terminal container with the browser's
`visualViewport` when a mobile soft keyboard opens/closes — can show as
resizing/zooming, a blank strip at the bottom, or scroll not matching the
visible screen. Tracked upstream: [tsl0922/ttyd#1531](https://github.com/tsl0922/ttyd/pull/1531)
(open, not merged; no ttyd release has it yet — the pinned `1.7.7` in the
`Dockerfile` is still the latest release, so there's no version to bump to).

Workarounds until upstream merges:

- Use a physical/Bluetooth keyboard — avoids triggering the soft keyboard.
- Landscape orientation is usually more stable than portrait.
- If the layout sticks after closing the keyboard, tap/focus the terminal
  once, or reload the page.

## Launcher is empty / wrong projects

1. Check `orcan.config.json` has `workspaces` with absolute `projects[].path`
2. Run `orcan sync` (terminal targets do not refresh config). Sync reconciles workspace meta on the host even when the container is down; live reconcile runs when the container is up.
3. `orcan down && orcan up` when `orcan doctor` reports a path not visible in the container.

If a project lived directly under the workspace folder (real directory instead of a symlink), `orcan sync` relocates it to `*.orcan-reconcile-bak` and recreates the symlink when the container is running (live reconcile). Check sync output for `relocated stale checkout dirs`.

Do **not** pass `PROJECT_DIR=…` on `orcan up`. Switch projects by editing config + `orcan sync`.

## `orcan sync` / `require-generated` fails

| Message | Fix |
| --- | --- |
| `.env` missing | `orcan sync` or `orcan init` |
| Generated files stale | Config is newer than `mounts/*` — run `orcan sync` |
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
grep DOCKER_GID "${ORCAN_HOME:-$HOME/.config/orcan}/.env"
orcan sync && orcan down && orcan up --with-docker
```

`orcan sync` re-detects the socket GID from the host (do not leave a stale `999` from `.env.example`).

## Path parity / nested Compose fails

See [Path parity](../concepts/path-parity.md). Confirm mounts with `orcan context show`.

## tmux keys do not work in the browser

## Embedded tmux does not resize with the browser

The cockpit PTY must own a controlling tty so resize delivers SIGWINCH to tmux. Fixed in current cockpit (`TIOCSCTTY` + `on_resize`). If the pane stays at attach size after a browser resize: update the image (`orcan build` / `make dev-restart`) and hard-refresh the tab. Details: [Terminal UI — cockpit](terminal-ui.md#cockpit-browser).

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

## Leftover `space/` is `root:root` after upgrading to 2.0

v2.0 renamed the managed projects root `space/` → `sandbox/`. If `.env` still
has `ORCAN_PROJECTS_ROOT=…/space` after the rename, the next `orcan up`
bind-mounts a **missing** host path and the Docker daemon creates it as
`root:root`. `orcan doctor` flags this (legacy `space/` check).

```bash
orcan down
# empty leftover (typical):
sudo rmdir "${ORCAN_DATA:-$HOME/.config/orcan}/space"
# or, if it still has your checkouts:
bash "${ORCAN_ROOT}/scripts/migrations/rename-space-to-sandbox.sh"
orcan sync && orcan down && orcan up
```

## Diagnostics checklist

```bash
orcan doctor
orcan context show
docker compose -f docker-compose.yml -f mounts/compose-projects.generated.yml config
orcan logs
```
