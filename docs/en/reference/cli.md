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
| `orcan migrate [--yes] [--no-symlink]` | Move configured projects under the managed root (`ORCAN_PROJECTS_ROOT`); dry-run unless `--yes` — fewer future container recreates |
| `orcan settings` | Edit tool settings (tmux windows/prefix, ttyd port/font) — separate from workspaces/projects |
| `orcan context show` | List workspaces + path-parity summary |
| `orcan context add PATH` | Add a project (`--workspace`, `--force`) |
| `orcan context tui` | TUI: scan a parent folder and build a compact **will add** selection. Every selected project can independently be mounted as-is or created as a managed worktree on one branch: **`t`** switches all selected git projects; in the **Tab** review, **`b`** switches only the highlighted project. **Enter** opens the highlighted folder while the selection is empty, then applies once projects are selected. The manage screen supports collapsible workspace groups with **←/→**. Default scan is direct children (`D` toggles grandchildren); `h` recalls recent picks. |
| `orcan context add --from-worktree REPO SELECTOR` | Add an existing git worktree (selector: branch, index, or path) |
| `orcan context worktrees [REPO]` | List git worktrees (`git worktree list`) |
| `orcan context worktree create …` | Create a worktree (managed under `$ORCAN_PROJECTS_ROOT/.worktrees` when `--workspace` is set) and pin it. If `--branch NAME` doesn't exist locally, a safe `git fetch origin NAME` is tried first (never prompts for credentials, 5s timeout) — found on the remote → worktree from that; not found/unreachable → new branch from `--start-point` (default `HEAD`), same as before |
| `orcan context worktree remove --path PATH` | Remove one managed worktree |
| `orcan context worktree remove --workspace NAME` | Remove all managed worktrees for a workspace (and unpin from config) |
| `orcan context worktree prune [--force] [--no-config]` | Reconcile `$ORCAN_PROJECTS_ROOT/.worktrees/registry.json` against disk (and `orcan.config.json`); dry-run by default, `--force` cleans up |
| `orcan studio probe --json` | Read-only, versioned host/runtime capability report for the separate Orcan Studio desktop application. It is designed for local, SSH, and WSL transports; it does not change config, images, or containers. |
| `orcan --instance NAME studio target register --yes` | Explicitly initialize host/container UUID metadata for an existing configuration; leaves its role and runtime unchanged. |
| `orcan studio target clone --yes` | Allocate a new host UUID on a cloned host. Then register each cloned instance with `register --new-target --yes`; original enclave references remain unchanged. |
| `orcan --instance NAME studio target verify --expected-host-id UUID --expected-id UUID` | Read-only UUID check used before native enclave Attach. |
| `orcan --instance NAME studio target replace-plan --expected-id UUID` | Preview archiving a named instance after Down. `replace-apply --expected-id UUID --yes` applies the archive; it never stops a runtime or deletes shared projects/data. |
| `orcan bundle create --output DIR [--image IMAGE]` | Create a clean, offline-installable host CLI kit. It excludes profiles, configuration, projects, sandbox data, and secrets; an optional local Docker image is saved alongside it. |
| `orcan studio parent plan --path PATH --branch BRANCH` | Read-only plan for updating a parent checkout; reports branch, dirty state, HEAD and `origin` head. |
| `orcan studio parent apply --path PATH --branch BRANCH --expected-head SHA --yes` | Apply an approved parent update with `git pull --ff-only`; refuses a stale, dirty, or wrong-branch checkout. |
| *(in-container)* `orcan-inbox` | Agent task handoff queue under `.orcan/tasks/` (`propose`, `approve`, `claim`, `complete`, `list`, `watch`). See [Agent inbox](../ideas/agent-inbox.md) |
| `orcan up [--web-terminal \| --web-terminal-auth USER:PASS] [--docker-socket \| --network NAME] [--ssh] [--github [--github-hostname HOST]] [--gitlab [--gitlab-hostname HOST]]` | Start container (`orcan enter` locally; pick **one** browser mode: `--web-terminal` or `--web-terminal-auth`); optional socket **or** network join (pick one) + SSH; hints if a newer release exists |
| `orcan down` | Stop containers |
| `orcan build --agent NAME [...] \| --all-agents [--force] [--no-cache] [--prune] [--remove-previous]` | Build `orcan:latest` + `orcan:<VERSION>` with explicit clients. `--prune` removes dangling Orcan images. `--remove-previous` asks `[y/n]` before removing previous local `orcan` tags/images after success; images used by containers are kept. Neither option deletes containers, sandbox data, workspaces, or BuildKit cache. Never publishes. |
| `orcan status` | Product version, runtime summary, and the image agent manifest |
| `orcan pull` | Pull portable all-agents `orcan:<VERSION>` → `orcan:latest` |
| `orcan publish` | Push an all-agents `orcan:latest` (**manual**; partial images are refused) |
| `orcan url` | Print browser terminal URL (requires `orcan up --web-terminal`) |
| `orcan enter` / `orcan go-in` | Local terminal into the running container (`--launcher` default, `--shell`, `--tmux [SESSION]`) |
| `orcan attach WORKSPACE` | Create or resume one configured workspace's tmux session and attach the current terminal. For a remote native terminal: `ssh -tt HOST 'orcan attach WORKSPACE'` |
| `orcan update` | Dev channel: fast-forward this checkout to `origin/main` |
| `orcan upgrade [--to VERSION]` | Release channel: newest release tag `vX.Y.Z` (default), or `--to` pins one (up or down) |
| `orcan downgrade [--to VERSION]` | Previous SemVer release, or pin an older `--to` (refuses newer targets) |
| `orcan uninstall [--purge-data] [--purge-images]` | Stop/remove Orcan runtime and CLI. Data/images are opt-in; `ORCAN_PROJECTS_ROOT` and configured projects are preserved |
| `orcan version` / `orcan help` | Version / help |

### Optional

| Command | Role |
| --- | --- |
| `orcan seed [--all] [--dry-run]` | Copy ignore/templates into git checkouts — **rarely needed**; the workspace context pack is enough |

## Ritual

```bash
orcan init
orcan build --agent codex
orcan up              # local — orcan enter on the same machine
# remote browser: orcan up --web-terminal
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
| `--web-terminal` \| `--web-terminal-auth USER:PASS` | **Pick one.** `--web-terminal`: browser terminal, no password. `--web-terminal-auth USER:PASS`: same browser terminal **with** HTTP basic auth. Do not pass both. (`TTYD_BIND` defaults to `0.0.0.0`.) |
| `--docker-socket` \| `--network NAME` | **Pick one.** `--docker-socket`: mount `/var/run/docker.sock` (Docker-from-Docker). `--network NAME`: join an existing Docker network (no socket) |
| `--resume` | Restart with the flags of the last `orcan up` (kept across `orcan down`, stored in `mounts/last-up.env`, never the ttyd password). A previous `--web-terminal-auth` start must pass `--web-terminal-auth USER:PASS` again. Orcan Studio Start/Restart use this. |
| `--github` | Provide a token to GitHub CLI in the selected container. Default host: `github.com`. |
| `--github-hostname HOST` | Select a GitHub hostname; requires `--github`. Use a hostname without a URL, path or port. |
| `--gitlab` | Provide a token to GitLab CLI in the selected container. Default host: `gitlab.com`. |
| `--gitlab-hostname HOST` | Select a GitLab hostname; requires `--gitlab`. Use a hostname without a URL, path or port. |
| `--ssh` | Mount host `~/.ssh` read-only (+ SSH agent when `SSH_AUTH_SOCK` is set) for push/pull |

The old names remain aliases: `--with-git` → `--ssh`, `--with-docker` →
`--docker-socket`, `--with-network` → `--network`, `--with-ttyd` →
`--web-terminal`, and `--with-ttyd-auth` → `--web-terminal-auth`.

### GitHub access

Authenticate on the host/VM that runs Orcan, then enable access explicitly:

```bash
gh auth login --hostname github.com
orcan up --github

# A company GitHub Enterprise Server
gh auth login --hostname github.company.example
orcan up --github --github-hostname github.company.example
```

Orcan first uses `GH_TOKEN` (or `GITHUB_TOKEN`) for `github.com` and `*.ghe.com`.
For another hostname it uses `GH_ENTERPRISE_TOKEN` (or `GITHUB_ENTERPRISE_TOKEN`).
If that token is absent, it requests the saved login for the exact hostname with
`gh auth token --hostname HOST`. Tokens from the other family are not reused.
Missing authentication stops the launch before the existing container is stopped.
These rules follow [GitHub CLI environment variables](https://cli.github.com/manual/gh_help_environment).

The token is passed in the container environment. It is not written to the
project config, generated Compose overlay or launch records. Agents in the
container and Docker administrators can access it. Limit its repository access
and permissions to the work you need. The token enables API operations such as
PR creation, comments and reviews; Git SSH access still uses `--ssh`.
`--github` does not change repository remotes or configure Git HTTPS credentials.
`--resume` retains the hostname and enabled flag, and resolves the token again.
Start without `--github` to recreate the container without this supplied token.
The same option is available for named instances (`orcan --instance reviewer up --github`).

### GitLab access

The image includes `glab` (GitLab CLI). Authenticate on the host/VM that runs
Orcan, then enable access explicitly:

```bash
glab auth login --hostname gitlab.com
orcan up --gitlab

# A company GitLab instance
glab auth login --hostname gitlab.company.example
orcan up --gitlab --gitlab-hostname gitlab.company.example

# Both services in one container
orcan up --github --gitlab --gitlab-hostname gitlab.company.example
```

Both public and company instances use `GITLAB_TOKEN`. Orcan also accepts
`GITLAB_ACCESS_TOKEN` and `OAUTH_TOKEN`, in that order after `GITLAB_TOKEN`.
Without an environment token, it requests the saved login for the selected host
with `glab config get token --host HOST`. CI job tokens are not used for this mode.
See [GitLab authentication](https://docs.gitlab.com/cli/authentication/).

As with GitHub, a missing token stops the launch before the current container is
stopped. The token is passed in the container environment, accessible to agents
and Docker administrators, and is absent from Orcan config, generated overlays
and launch records. Scope it to the required projects and operations. `--resume`
remembers the hostname and resolves the token again. Starting without `--gitlab`
removes this supplied access. GitLab and GitHub access can be enabled separately
or together. `--gitlab` does not modify remotes or Git HTTPS credentials; SSH
access continues to use `--ssh`. Update/rebuild the runtime image to obtain `glab`.

Other flags combine with a chosen browser mode, e.g. `orcan up --web-terminal --ssh` or `orcan up --web-terminal-auth user:pass --network my-net`.

Git **author** identity is always synced by `orcan sync` (`GIT_AUTHOR_*` from host `user.name` / `user.email`). SSH keys are only attached with `--ssh`. Optional flags print a security warning — agents inside can use the mounted socket or keys. Capability ladder and mount tradeoffs: [Security](security.md), [Workflows](../guides/workflows.md).

## Maintainer Make

From a git checkout: `make validate`, `make test-host`, `make docs*`, `make release*`, `make registry-*`. See [Development](../development/overview.md).
