---
description: Short answers about Orcan — models, images, update, uninstall, bugs, and contributing.
---

# FAQ

Short answers to common Orcan questions.

## What is Orcan?

Orcan is a **work-context orchestrator**. It runs Cursor CLI (`agent`) and Claude Code (`claude`) in Docker with workspaces (named sets of projects) and path-parity mounts. Enter locally with `orcan enter`, or optionally use a browser terminal (`orcan up --with-ttyd`).

Read [Why Orcan?](why-orcan.md) and [Core Ideas](ideas/core-ideas.md) before the rest of this FAQ.

## Does Orcan choose AI models?

**No.** Models stay with each CLI / account. Orcan does not pin or route models.

## How do I switch projects?

Edit `orcan.config.json` (or `orcan init`), then:

```bash
orcan sync
orcan down && orcan up
```

Do **not** pass `PROJECT_DIR=…` to `orcan up`.

## Why does `orcan up` ignore my config edits?

`orcan up` does not run `orcan sync`. Always apply config first.

## Can I customize aliases / tmux / vim?

**Yes.** Put overlays in `$ORCAN_DATA/dotfiles` (default `~/.config/orcan/dotfiles`). Image defaults stay; your files are bind-mounted. See [User dotfiles](guides/dotfiles.md). For the shared navy/cyan look (tmux, starship, lazygit, …): [Terminal UI](guides/terminal-ui.md).

## Must I use the browser (ttyd)?

**No.** ttyd is great for remote / phone. Locally use `orcan enter` (or `orcan go-in`) — workspace picker by default; `--tmux` / `--shell` for other modes. See [Workflows — local terminal](guides/workflows.md#local-terminal).

## Why does ttyd say “reconnecting” on mobile / in the car?

WebSocket drops on cellular handoffs are normal. **tmux sessions and agents keep running** — only the browser client reconnects.

After reconnect, the launcher **auto-reattaches** to the last workspace (2s countdown; press Enter for the menu). Disable with `ORCAN_AUTO_REATTACH=0` in the container environment. Ping interval defaults to 20s (`TTYD_PING_INTERVAL` / `ttyd.ping_interval`).

## Can I commit and push from inside the container?

**Commit author:** yes after `orcan sync` — host `user.name` / `user.email` become `GIT_AUTHOR_*` in the container.

**Push/pull over SSH:** start with `orcan up --with-git` (mounts `~/.ssh`, and the SSH agent when available). Combine with DinD: `orcan up --with-docker --with-git`. Plain `orcan up` does not attach keys. See [Quickstart](getting-started/quickstart.md#git-inside-the-container) and [Security](reference/security.md).

**Worktrees:** optional. Mount a normal clone path by default; use the wizard’s advanced help or `orcan context worktree` when you want a separate checkout under `$ORCAN_PROJECTS_ROOT/.worktrees` (default `~/.config/orcan/sandbox/.worktrees` — covered by the stable projects mount, so no container recreate). See [Workspaces](concepts/workspaces.md#git-worktrees).

## Which agents are installed?

By default the image includes **both** agents (`orcan:latest` / `orcan:<VERSION>`). To skip installing an agent you will not use, build a **separate local tag** (no registry pull; does not overwrite `latest`):

=== "Both (default)"

    ```bash
    orcan build
    orcan up
    ```

=== "Claude Code only"

    ```bash
    orcan build --claude
    IMAGE_LOCAL=orcan:0.1.1-claude orcan up   # use your VERSION from the build output
    ```

    Tag: `orcan:<VERSION>-claude`. Cursor CLI is not installed.

=== "Cursor CLI only"

    ```bash
    orcan build --cursor
    IMAGE_LOCAL=orcan:0.1.1-cursor orcan up
    ```

    Tag: `orcan:<VERSION>-cursor`. Claude Code is not installed.

## Is there a published Docker image?

**Not from CI.** Registry holds **both-agents** as `orcan:<VERSION>` / `:latest`. Single-agent `-<claude|cursor>` tags are local only. `orcan publish` pushes only both-agents images.

## Where is my login / cache data?

Under `$ORCAN_DATA` (default `~/.config/orcan`):

| Host path | What |
| --- | --- |
| `claude/` | Claude Code config + OAuth (`.credentials.json`, settings). `CLAUDE_CONFIG_DIR` points here so login survives restarts |
| `cursor/` | Cursor CLI home |
| `codex/` | Codex CLI home |
| `cache/` | All tool caches under container `~/.cache` (npm, pnpm, cargo, go, uv, …) |
| `history/` | Shell history (`HISTFILE`) |
| `dotfiles/` | Personal shell/tmux/vim overlays |

Browse the sandbox map inside the container at `~/orcan-map/` (symlinks only).

After `orcan build --force` / restart, you should **not** need to `/login` again unless you wiped `$ORCAN_DATA` or never completed login while the volume was mounted.

## Can I turn off tmux?

Not as a supported switch. The launcher starts tmux. Use multiple tmux windows/panes instead.

## How do I update?

```bash
orcan update                         # newest release tag vX.Y.Z
orcan sync                           # when config schema changed
orcan build --force                  # when Dockerfile/rootfs changed
orcan down && orcan up
```

## How do I uninstall? { #uninstall }

```bash
cd /absolute/path/to/orcan
orcan down
orcan uninstall --purge-data          # destructive: deletes ~/.config/orcan (type yes)
docker images 'orcan*'   # optional: docker rmi …
# then remove the git clone directory if you no longer need it
```

Details: [Workflows — uninstall](guides/workflows.md#uninstall).

## How do I report a bug?

Open a GitHub Issue with OS, Docker version, the `orcan` command you ran, and relevant logs (`orcan logs`, `orcan doctor`, `orcan context show`):

https://github.com/aKyther/orcan/issues

## How do I contribute / add code?

1. Read [Contributing](https://github.com/aKyther/orcan/blob/main/CONTRIBUTING.md).
2. Follow [Development overview](development/overview.md).
3. Open a PR against `main`.

## See also

- [Quick start](getting-started/quickstart.md)
- [Troubleshooting](guides/troubleshooting.md)
- [Configuration](getting-started/configuration.md)
- [GitHub Issues](https://github.com/aKyther/orcan/issues)
