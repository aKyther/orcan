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
| Bash, Git | CLI, install, `orcan update` |
| **Python 3** | `orcan sync`, `init`, `context` (show / add / hook) |
| Docker Compose v2 | `orcan build`, `up`, `down`, … |

Check with `orcan doctor`. Details: [Installation](../getting-started/installation.md).

## Commands

| Command | Role |
| --- | --- |
| `orcan init` | No PATH: TUI to create/edit workspaces (default) + sync + show. `--cli`: old sequential prompt wizard instead |
| `orcan init PATH` | Non-interactive: scaffold a single project (scripts/CI) + sync + show |
| `orcan sync` | Apply `orcan.config.json` → `.env` + `mounts/*` |
| `orcan settings` | Edit tool settings (tmux windows/prefix, ttyd port/font) — separate from workspaces/projects |
| `orcan context show` | List workspaces + path-parity summary |
| `orcan context add PATH` | Add a project (`--workspace`, `--force`) |
| `orcan context tui` | TUI: scan a parent folder, multi-select repos, create/update a workspace; optional one branch → managed worktree per repo (`--sync`, `--yes`). With an existing config it opens in **manage mode** instead — rename/move/delete existing workspaces and projects (`n` switches to the scan screen to add more); this is what `orcan init` runs by default |
| `orcan context add --from-worktree REPO SELECTOR` | Add an existing git worktree (selector: branch, index, or path) |
| `orcan context worktrees [REPO]` | List git worktrees (`git worktree list`) |
| `orcan context worktree create …` | Create a worktree (managed under `$ORCAN_DATA/worktrees` when `--workspace` is set) and pin it |
| `orcan context worktree remove --path PATH` | Remove one managed worktree |
| `orcan context worktree remove --workspace NAME` | Remove all managed worktrees for a workspace (and unpin from config) |
| `orcan context worktree prune [--force] [--no-config]` | Reconcile `$ORCAN_DATA/worktrees/registry.json` against disk (and `orcan.config.json`); dry-run by default, `--force` cleans up |
| `orcan context assert propose …` | Reflection: draft a Context Assertion (content + justification + applicability); status `proposed` |
| `orcan context assert accept\|reject\|retire ID` | Review Gate: `proposed` → `accepted`/`rejected`, or `accepted` → `retired` — never automatic |
| `orcan context assert list\|show\|select\|root` | Inspect the store; `select` previews what `orcan sync` would compile |
| `orcan context hook enable\|disable\|status [WORKSPACE ...] [--all]` | Toggle the Claude `Stop` hook (batched Reflection) in the workspace's generated root `.claude/settings.json` — **on by default**, seeded by the first `orcan sync` for a workspace; `disable` sticks across later syncs. With no `WORKSPACE`/`--all`, infers the workspace from cwd when it's inside a registered project |
| *(in-container)* `orcan-context-propose` / `orcan-context-review` | Draft/review without a host terminal — drop into a mounted inbox, imported by the next `orcan sync`. `orcan-context-review [--no-check]` pre-checks candidates against `CONTEXT-ASSERTIONS.md` for duplicates/conflicts (nudge only, never a gate). See [Context Assertions](../ideas/context-assertions.md) |
| `orcan up [--with-docker] [--with-git] [--with-network NAME]` | Start browser terminal (socket / host SSH / network join only with flags); hints if a newer release exists; once ready, prints the workspace's Claude `Stop` hook status |
| `orcan down` | Stop containers |
| `orcan build [--claude|--cursor] [--force] [--no-cache]` | Both agents → `orcan:latest` + `orcan:<VERSION>` (pull or build). `--claude` / `--cursor` → `orcan:<VERSION>-claude\|cursor` (no pull; does not overwrite `latest`). Never publishes |
| `orcan pull` | Pull both-agents `orcan:<VERSION>` → `orcan:latest` |
| `orcan publish` | Push both-agents `orcan:latest` (**manual**; not `-claude`/`-cursor`) |
| `orcan url` | Print terminal URL |
| `orcan logs` | Follow logs |
| `orcan enter` / `orcan go-in` | Local terminal into the running container (`--launcher` default, `--shell`, `--tmux [SESSION]`) |
| `orcan update [--release\|--main]` | Newest release tag `vX.Y.Z` (default); `--main` for bleeding edge |
| `orcan doctor` | Host / config health report |
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
orcan up
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
| *(none)* | Browser terminal only — no Docker socket, no host SSH |
| `--with-docker` | Mount `/var/run/docker.sock` (Docker-from-Docker) |
| `--with-git` | Mount host `~/.ssh` read-only (+ SSH agent when `SSH_AUTH_SOCK` is set) for push/pull |
| `--with-network NAME` | Join an existing Docker network (e.g. another project's compose stack) — no socket mount, lower-risk alternative to `--with-docker` when you only need reachability |

Flags combine: `orcan up --with-docker --with-git --with-network my-net`.

Git **author** identity is always synced by `orcan sync` (`GIT_AUTHOR_*` from host `user.name` / `user.email`). SSH keys are only attached with `--with-git`. Both optional flags print a security warning — agents inside can use the mounted socket or keys. See [Security](security.md) and [Workflows](../guides/workflows.md).

## Maintainer Make

From a git checkout: `make validate`, `make test-host`, `make docs*`, `make release*`, `make registry-*`. See [Development](../development/overview.md).
