---
description: Public orcan CLI — commands, flags, and maintainer vs end-user boundary.
tags:
  - reference
---

# CLI reference

Public interface for Orcan is the **`orcan`** command (Bash). Make targets remain for **maintainers** only (docs, tests, release).

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/aKyther/orcan/main/install.sh | bash
```

| Path | Role |
| --- | --- |
| `~/.local/share/orcan` | Git clone (`ORCAN_ROOT`) |
| `~/.local/bin/orcan` | Launcher |
| `~/.config/orcan` | Config + `.env` + `mounts/*` (`ORCAN_HOME`) *and* tool data / logins (`ORCAN_DATA`) — same root by default |

Override only if needed: `ORCAN_HOME=/path` or `ORCAN_USE_CWD=1` (use `./orcan.config.json` in the current directory).

## Host dependencies

The `orcan` command is **Bash**, but config work on the host uses **Python 3** (stdlib only — no pip/venv):

| Need | Used by |
| --- | --- |
| Bash, Git | CLI, install, `orcan update`/`upgrade`/`downgrade` |
| **Python 3** | `orcan sync`, `init`, `context` (show / add / hook) |
| Docker Compose v2 | `orcan build`, `up`, `down`, … |

Check with `orcan doctor`. Details: [Installation](../getting-started/installation.md).

## Commands

| Command | Role |
| --- | --- |
| `orcan init` | No PATH: TUI to create/edit workspaces (default) + sync + show. `--cli`: old sequential prompt wizard instead |
| `orcan init PATH` | Non-interactive: scaffold a single project (scripts/CI) + sync + show |
| `orcan sync [--prune-orphans]` | Apply `orcan.config.json` → `.env` + `mounts/*`; live-reconciles a running container. `--prune-orphans` also kills orphaned tmux sessions from a removed/renamed workspace (default: report only) |
| `orcan sync --context [--watch\|--once] [--force] [--interval N]` | Host-only: compile/import Context Assertion inbox drops without a full config sync (`scripts/repository/context_syncd.py`). `--once` skips when the inbox fingerprint is unchanged; `--watch` polls (default 15s). Respects cockpit **`[p]`** pause / **`[o]`** off via `$ORCAN_DATA/history/supervisor/automation.json`. See [Context Assertions](../ideas/context-assertions.md) |
| `orcan migrate [--yes] [--no-symlink]` | Move configured projects under the managed root (`ORCAN_PROJECTS_ROOT`); dry-run unless `--yes` — fewer future container recreates |
| `orcan settings` | Edit tool settings (tmux windows/prefix, ttyd port/font) — separate from workspaces/projects |
| `orcan context show` | List workspaces + path-parity summary |
| `orcan context add PATH` | Add a project (`--workspace`, `--force`) |
| `orcan context tui` | TUI: scan a parent folder, multi-select repos, create/update a workspace; optional one branch → managed worktree per repo (`--sync`, `--yes`). With an existing config it opens in **manage mode** instead — rename/move/delete existing workspaces and projects (`n` switches to the scan screen to add more); this is what `orcan init` runs by default |
| `orcan context add --from-worktree REPO SELECTOR` | Add an existing git worktree (selector: branch, index, or path) |
| `orcan context worktrees [REPO]` | List git worktrees (`git worktree list`) |
| `orcan context worktree create …` | Create a worktree (managed under `$ORCAN_PROJECTS_ROOT/.worktrees` when `--workspace` is set) and pin it. If `--branch NAME` doesn't exist locally, a safe `git fetch origin NAME` is tried first (never prompts for credentials, 5s timeout) — found on the remote → worktree from that; not found/unreachable → new branch from `--start-point` (default `HEAD`), same as before |
| `orcan context worktree remove --path PATH` | Remove one managed worktree |
| `orcan context worktree remove --workspace NAME` | Remove all managed worktrees for a workspace (and unpin from config) |
| `orcan context worktree prune [--force] [--no-config]` | Reconcile `$ORCAN_PROJECTS_ROOT/.worktrees/registry.json` against disk (and `orcan.config.json`); dry-run by default, `--force` cleans up |
| `orcan context assert propose …` | Reflection: draft a Context Assertion (content + justification + applicability); status `proposed` |
| `orcan context assert accept\|reject\|retire ID` | Review Gate: `proposed` → `accepted`/`rejected`, or `accepted` → `retired` — never automatic |
| `orcan context assert list\|show\|select\|root` | Inspect the store; `select` previews what `orcan sync` would compile |
| `orcan context hook enable\|disable\|status [WORKSPACE ...] [--all]` | Toggle the Claude `Stop` hook (batched Reflection) in the workspace's generated root `.claude/settings.json` — **on by default**, seeded by the first `orcan sync` for a workspace; `disable` sticks across later syncs. With no `WORKSPACE`/`--all`, infers the workspace from cwd when it's inside a registered project |
| *(in-container)* `orcan-context-propose` / `orcan-context-review` | Draft/review without a host terminal — drop into a mounted inbox, imported by the next `orcan sync`. `orcan-context-review [--no-check]` pre-checks candidates against `CONTEXT-ASSERTIONS.md` for duplicates/conflicts (nudge only, never a gate). See [Context Assertions](../ideas/context-assertions.md) |
| *(in-container)* `orcan-context-scan` | Filesystem Reflection feeder (`--watch`, `--all-workspaces`); default driver **recap** via `orcan-context-recap`. See [Context Assertions](../ideas/context-assertions.md) |
| *(in-container)* `orcan-context-recap` | Cascading session compact + inbox flush (invoked by scan; not usually run manually). See [Context Assertions](../ideas/context-assertions.md) |
| *(in-container)* `orcan-context-model-check` | Probe Claude/Haiku for recap; `--quick` (PATH/version), `--refresh` (update `automation.json` cache). See [Context Assertions](../ideas/context-assertions.md) |
| *(in-container)* `orcan-inbox` | Agent task handoff queue under `.orcan/tasks/` (`propose`, `approve`, `claim`, `complete`, `list`, `watch`). See [Agent inbox](../ideas/agent-inbox.md) |
| `orcan up [--with-ttyd \| --with-ttyd-auth USER:PASS] [--with-docker \| --with-network NAME] [--with-git]` | Start container (`orcan enter` locally; pick **one** browser mode: `--with-ttyd` or `--with-ttyd-auth`); optional socket **or** network join (pick one) + SSH; hints if a newer release exists; prints Claude `Stop` hook status when a workspace is configured |
| `orcan down` | Stop containers |
| `orcan build [--claude|--cursor] [--force] [--no-cache]` | Both agents → `orcan:latest` + `orcan:<VERSION>` (pull or build). `--claude` / `--cursor` → `orcan:<VERSION>-claude\|cursor` (no pull; does not overwrite `latest`). Never publishes |
| `orcan pull` | Pull both-agents `orcan:<VERSION>` → `orcan:latest` |
| `orcan publish` | Push both-agents `orcan:latest` (**manual**; not `-claude`/`-cursor`) |
| `orcan url` | Print browser terminal URL (requires `orcan up --with-ttyd`) |
| `orcan logs [docker\|supervisor\|context-scan]` | Follow container stdout (default) or show durable supervisord / Reflection scanner logs |
| `orcan enter` / `orcan go-in` | Local terminal into the running container (`--launcher` default, `--shell`, `--tmux [SESSION]`) |
| `orcan update` | Dev channel: fast-forward this checkout to `origin/main` |
| `orcan upgrade [--to VERSION]` | Release channel: newest release tag `vX.Y.Z` (default), or `--to` pins one (up or down) |
| `orcan downgrade [--to VERSION]` | Previous SemVer release, or pin an older `--to` (refuses newer targets) |
| `orcan doctor` | Host / config / container health (supervisord, context automation state, recap model probe when the image supports them) |
| `orcan uninstall [--purge-data]` | Remove CLI (optional wipe of `ORCAN_DATA`) |
| `orcan version` / `orcan help` | Version / help |

### Optional

| Command | Role |
| --- | --- |
| `orcan seed [--all] [--dry-run]` | Copy ignore/templates into git checkouts — **rarely needed**; the workspace context pack is enough |

## Ritual

```bash
orcan init
orcan build
orcan up              # local — orcan enter on the same machine
# remote browser: orcan up --with-ttyd
```

After config edits:

```bash
# edit ~/.config/orcan/orcan.config.json
orcan sync
orcan down && orcan up
```

`orcan up` does **not** run `sync`.

### `orcan up` flags

| Flag | Effect |
| --- | --- |
| *(none)* | Local-only container — no published ttyd port; use `orcan enter` |
| `--with-ttyd` \| `--with-ttyd-auth USER:PASS` | **Pick one.** `--with-ttyd`: browser terminal, no password. `--with-ttyd-auth USER:PASS`: same browser terminal **with** HTTP basic auth. Do not pass both. (`TTYD_BIND` defaults to `0.0.0.0`.) |
| `--with-docker` \| `--with-network NAME` | **Pick one.** `--with-docker`: mount `/var/run/docker.sock` (Docker-from-Docker). `--with-network NAME`: join an existing Docker network (no socket) |
| `--with-git` | Mount host `~/.ssh` read-only (+ SSH agent when `SSH_AUTH_SOCK` is set) for push/pull |

Other flags combine with a chosen browser mode, e.g. `orcan up --with-ttyd --with-git` or `orcan up --with-ttyd-auth user:pass --with-network my-net`.

Git **author** identity is always synced by `orcan sync` (`GIT_AUTHOR_*` from host `user.name` / `user.email`). SSH keys are only attached with `--with-git`. Optional flags print a security warning — agents inside can use the mounted socket or keys. Capability ladder and mount tradeoffs: [Security](security.md), [Workflows](../guides/workflows.md).

## Maintainer Make

From a git checkout: `make validate`, `make test-host`, `make docs*`, `make release*`, `make registry-*`. See [Development](../development/overview.md).
