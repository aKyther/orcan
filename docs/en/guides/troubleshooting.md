# Troubleshooting

Start with the symptom below. Unless a section says otherwise, run commands in
your computer's terminal, outside Orcan (the **host terminal**). Use Cockpit's
**Exit** button to return there. On Windows, use your WSL2 Linux terminal.

## Start with a simple check

```bash
orcan doctor
orcan status
```

These reports help identify missing tools, configuration, images and runtime
state. You can run them from any folder; no Orcan source checkout is needed.
For an unfinished setup, return to the failed step in
[Your first session](../getting-started/quickstart.md).

## `orcan: command not found` { #orcan-command-not-found }

After installation, open a new terminal and try `orcan doctor` again. If the
command is still missing, try in that terminal:

```bash
export PATH="$HOME/.local/bin:$PATH"
orcan doctor
```

If that works, your shell was not finding the install folder. If it still fails,
review the installer result and follow [Installation](../getting-started/installation.md).

## Docker is not running or access is denied

Start Docker, then run `docker version` in the same terminal as Orcan.
On Windows, check that Docker is available to the selected WSL2 distribution.

An access-denied error means your user cannot use Docker. Follow your Docker
installation's user-access instructions (rootless Docker or Docker group access
on Linux). Ask the person who manages the computer if you cannot change this.

## Orcan will not start

If the error says configuration or generated files are missing, follow
[First session, steps 1–2](../getting-started/quickstart.md#1-choose-your-project).
If it says the image is missing, complete step 3. `orcan up` starts prepared
files and an existing image; it does not configure or build them automatically.

If Docker is ready and setup is complete, inspect `orcan logs` for the startup
error. Share only the relevant error when requesting help.

## The agent asks me to sign in

Start the installed agent inside your project folder and follow its sign-in
prompts. Your Orcan installation and agent account are separate. Account access,
subscription and usage limits belong to that provider.

If the agent needs a browser, use the link or code it provides. Never post
sign-in codes, tokens or passwords in a bug report.

## Launcher is empty / wrong projects

Run `orcan context show` in the host terminal. Check that your workspace lists
the folder you intended to connect. To add or correct it, follow
[Configuration](../getting-started/configuration.md#change-settings-without-editing-files),
then run `orcan sync`.

If Orcan reports that the folder is not visible in the container, finish active
work, run `orcan down`, then `orcan up` and `orcan enter`.
In Cockpit, press **F4** to choose the configured workspace.

For existing installations with a misplaced checkout inside workspace metadata,
see [Project folder locations](workflows.md#scenario-optional-git-worktree).

## Agent or Claude missing

Run `orcan status` in the host terminal to check which agents are installed.
If yours is missing, prepare it using
[First session, step 3](../getting-started/quickstart.md#3-prepare-your-agent).

A running container still uses its previous image. Finish active work and stop
it with `orcan down`, then run `orcan up` and `orcan enter`. Launch the agent
inside your project folder. See [Daily use](daily-use.md) for stopping and returning.

## Ask for help

If the sections below do not solve the problem, open an
[Orcan issue](https://github.com/aKyther/orcan/issues). Include your operating
system, the command you ran, what you expected, the relevant error and your
Orcan version from `orcan status`. Mention whether you are on WSL2 or a remote host.
Review diagnostic output before sharing it; omit credentials and private paths.

## Additional problems

The following sections cover project selection, optional browser access and
advanced setups.

## Browser terminal will not open

Requires `orcan up --web-terminal` (plain `orcan up` is local-only — use `orcan enter` instead).

1. Confirm the container is up: `orcan logs`
2. Confirm ttyd is on: `orcan doctor` (Runtime section) or `orcan url`
3. Confirm the URL: `orcan url` (prints `http://localhost:7681` when `TTYD_BIND` is `0.0.0.0`)
4. If the port is busy, change `ttyd.host_port` in `orcan.config.json`, then `orcan sync` and `orcan down && orcan up --web-terminal`

## Frequent “reconnecting” on phone / mobile network

Cellular handoffs drop the ttyd WebSocket; that is expected. Processes inside tmux survive.

- After reconnect, `agent-launcher` retries the last workspace while the picker is loading. If its embedded terminal does not answer, Cockpit returns to the workspace picker; choose the workspace again.
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

## `orcan sync` / `require-generated` fails

| Message | Fix |
| --- | --- |
| Runtime JSON missing | `orcan sync` (after saving configuration with `orcan init` if needed) |
| Generated files stale | Config is newer than `mounts/*` — run `orcan sync` |
| Invalid `PROJECT_DIR` | Absolute path; avoid `/`, `/home`, `/etc` |

## Docker socket errors inside the container

Use `orcan up --docker-socket`. Plain `orcan up` does not mount the socket.

If `docker` needs `sudo` inside the container, the host socket GID must match the detected `DOCKER_GID`:

```bash
stat -c '%g' /var/run/docker.sock
orcan sync && orcan down && orcan up --docker-socket
```

The CLI detects the socket GID from the host at launch; no dotenv value is used.

## Path parity / nested Compose fails

See [Path parity](../concepts/path-parity.md). Confirm mounts with `orcan context show`.

## tmux keys do not work in the browser

Press **F1** in Cockpit for supported shortcuts. Browser shortcuts can intercept
terminal keys; see [Terminal UI](terminal-ui.md#cockpit-nav-mix) for alternatives.

## Embedded tmux does not resize with the browser

The cockpit PTY must own a controlling tty so resize delivers SIGWINCH to tmux. Fixed in current cockpit (`TIOCSCTTY` + `on_resize`). If the pane stays at attach size after a browser resize: update the image (`orcan build --agent codex`, then recreate the container) and hard-refresh the tab. Details: [Terminal UI — cockpit](terminal-ui.md#cockpit-browser).

## Long URL wraps and is hard to click

Browser/terminal linkify usually matches **one screen row**. Soft-wrapped `https://…` links break into pieces, so click-to-open fails.

Workaround (image default): **prefix `u`** (`C-Space` then `u`) — joins wrapped lines in the pane, then copies the URL (menu if several). Paste with prefix `]` or the browser paste shortcut.

Apps that emit OSC 8 hyperlinks can stay clickable across wraps when the outer terminal supports them; plain printed URLs still need prefix `u`.

## “Disable tmux” / plain shell only

tmux is started by the launcher (`cursor-ttyd` → `agent-launcher`), not by a block in `50-orcan-shell.zsh`. There is no supported “turn off tmux” switch today. You can still open extra shells inside tmux windows.

## Host `~/.gitconfig` became a directory

An older layout could create a root-owned directory. Fix ownership or replace with a normal file, then update Orcan and recreate the container.

Orcan does **not** mount host `~/.gitconfig`. Instead `orcan sync` copies `user.name` / `user.email` into generated host settings. Compose forwards the identity as `ORCAN_GIT_USER_NAME` / `ORCAN_GIT_USER_EMAIL`; startup writes global Git defaults without forcing commit environment variables.

For separate GitHub and GitLab identities, run these commands in each repository:

```bash
git config --local user.name "Your Name"
git config --local user.email "you@example.com"
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
```

Conditional includes in the container Git configuration also work. Host `~/.gitconfig` includes are not copied automatically. This change requires an updated runtime image and a recreated container; restarting an old image is not enough. Existing terminal sessions keep their old environment.

For `git push` / `git pull` over SSH:

```bash
orcan up --ssh
# combine with DinD:
orcan up --docker-socket --ssh
```

That mounts host `~/.ssh` read-only (and the SSH agent when `SSH_AUTH_SOCK` is set). Plain `orcan up` does not.

## Leftover `space/` is `root:root` after upgrading to 2.0

v2.0 renamed the managed projects root `space/` → `sandbox/`. If `projects_root` in JSON still
points at `…/space` after the rename, the next `orcan up`
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
