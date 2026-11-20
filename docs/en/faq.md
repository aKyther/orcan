---
description: Short answers about Orcan — models, images, update, uninstall, bugs, and contributing.
---

# FAQ

Short answers to common Orcan questions.

## What is Orcan?

Orcan is a **work-context orchestrator**. It runs Cursor CLI (`agent`) and Claude Code (`claude`) in Docker with workspaces (named sets of projects) and path-parity mounts. Enter locally with `orcan enter`, or optionally use a browser terminal (`orcan up --web-terminal`).

Start with [Installation](getting-started/installation.md) and
[Your first session](getting-started/quickstart.md). For returning tomorrow, see
[Daily use](guides/daily-use.md).

## Does Orcan choose AI models?

**No.** Models stay with each CLI / account. Orcan does not pin or route models.

## How do I switch projects?

Use **F4** for an existing workspace. To connect another project, follow
[Daily use — switch projects](guides/daily-use.md#switch-workspaces-or-open-another-project).

## Why does `orcan up` ignore my config edits?

`orcan up` does not run `orcan sync`. Always apply config first.

## Can I customize aliases / tmux / vim?

**Yes.** Put overlays in `$ORCAN_DATA/dotfiles` (default `~/.config/orcan/dotfiles`). Image defaults stay; your files are bind-mounted. See [User dotfiles](guides/dotfiles.md). For the shared Warm Graphite / Amber terminal look (tmux, starship, lazygit, …): [Terminal UI](guides/terminal-ui.md).

## Must I use the browser (ttyd)?

**No.** ttyd is great for remote / phone. Locally use `orcan enter` (or `orcan go-in`) — the cockpit (top bar: rail + metrics \| main: workspaces \| tmux) by default; `--tmux` / `--shell` for other modes. See [Workflows — local terminal](guides/workflows.md#local-terminal).

## Why does ttyd say “reconnecting” on mobile / in the car?

WebSocket drops on cellular handoffs are normal. **tmux sessions and agents keep running** — only the browser client reconnects.

After reconnect, the launcher retries the last workspace while its list is becoming ready. If the embedded terminal does not answer, it returns to the workspace picker instead of staying on a loading screen. Ping interval defaults to 20s (`TTYD_PING_INTERVAL` / `ttyd.ping_interval`).

## Can I commit and push from inside the container?

**Commit author:** host `user.name` / `user.email` provide container Git defaults after sync and container creation. Repository settings can override them.

**Push/pull over SSH:** start with `orcan up --ssh` (mounts `~/.ssh`, and the SSH agent when available). Combine with DinD: `orcan up --docker-socket --ssh`. Plain `orcan up` does not attach keys. See [Quickstart](getting-started/quickstart.md#git-inside-the-container) and [Security](reference/security.md).

**Worktrees:** optional. Mount a normal clone path by default; use the wizard’s advanced help or `orcan context worktree` when you want a separate checkout under `$ORCAN_PROJECTS_ROOT/.worktrees` (default `~/.config/orcan/sandbox/.worktrees` — covered by the stable projects mount, so no container recreate). See [Workspaces](concepts/workspaces.md#git-worktrees).

## Which agents are installed?

Choose an agent when preparing Orcan. Follow the choices in
[Your first session](getting-started/quickstart.md#3-prepare-your-agent).
For several agents or extra tools, see [Image profiles](guides/image-profiles.md).
Run `orcan status` to inspect the installed selection.

## Is there a published Docker image?

**Not from CI.** A registry image is portable only when its manifest enables every supported client. `orcan publish` refuses partial images.

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

After `orcan build --agent codex --force` / restart, you should **not** need to `/login` again unless you wiped `$ORCAN_DATA` or never completed login while the volume was mounted.

## Can I turn off tmux?

Not as a supported switch. The launcher starts tmux. Use multiple tmux windows/panes instead.

## How do I update?

See [Upgrade / downgrade Orcan](guides/workflows.md#upgrade-downgrade-orcan)
for the update procedure and when to rebuild your environment.

## How do I uninstall? { #uninstall }

See [Uninstall](guides/workflows.md#uninstall) for removal options and which data
each option preserves. Read that section before choosing to remove saved data.

## How do I report a bug?

Follow [Ask for help](guides/troubleshooting.md#ask-for-help) for what to include
in an Orcan issue.

## How do I contribute / add code?

1. Read [Contributing](https://github.com/aKyther/orcan/blob/main/CONTRIBUTING.md).
2. Follow [Development overview](development/overview.md).
3. Open a PR against `main`.

## See also

- [Quick start](getting-started/quickstart.md)
- [Troubleshooting](guides/troubleshooting.md)
- [Configuration](getting-started/configuration.md)
- [GitHub Issues](https://github.com/aKyther/orcan/issues)
