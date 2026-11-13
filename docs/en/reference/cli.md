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
| `~/.config/orcan` | Config + runtime JSON + `mounts/*` (`ORCAN_HOME`) *and* tool data / logins (`ORCAN_DATA`) — same root by default |

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
| `orcan init` | No PATH: TUI to create/edit workspaces (default) + show; run `orcan sync` separately. `--cli`: old sequential prompt wizard instead |
| `orcan init PATH` | Non-interactive: scaffold a single project (scripts/CI) + show; run `orcan sync` separately |
| `orcan sync [--prune-orphans] [--no-chown PATTERN] [--chown-exclude /absolute/path]` | Apply `orcan.config.json` → runtime JSON + `mounts/*`; live-reconciles a running container. `--prune-orphans` also kills orphaned tmux sessions from a removed/renamed workspace (default: report only). Use `--no-chown "external"` to skip ownership changes for every matching name at any depth under the data root, including its subtree. Quoted shell-style globs such as `--no-chown "external*"` are supported and case-sensitive; patterns contain no slashes. Repeat either flag for multiple exclusions. Repeat `--chown-exclude` to skip ownership changes for directories and their contents, such as SSHFS mounts. Exclusions are saved in `orcan.config.json` under `ownership.excluded_names` and `ownership.excluded_paths`, and apply to every later sync. `init` saves configuration without running sync. Remove entries there to re-enable ownership changes. They do not remove projects from the workspace. |
| `orcan migrate [--yes] [--no-symlink]` | Move configured projects under the managed root (`ORCAN_PROJECTS_ROOT`); dry-run unless `--yes` — fewer future container recreates |
| `orcan settings [--cli]` | Terminal UI for startup plugins, agent/image selection, container and tmux settings, with review/save and a workspace-manager entry. `--cli` retains the sequential wizard. |
| `orcan sandbox pull [--dry-run] [--root /absolute/path] [--exclude PATTERN] [--timeout SECONDS] [--json]` | Recursively discover parent Git checkouts and pull their current upstream with `--ff-only`, without rebase, autostash or submodule recursion. Skip dirty parents, worktrees, bare repos, detached HEAD, ongoing Git operations and missing upstreams. Continue after errors; return 1 if any repository fails. Dry-run does not fetch or change refs. |
| `orcan context show` | List workspaces + path-parity summary |
| `orcan context add PATH` | Add a project (`--workspace`, `--force`) |
| `orcan context tui` | Vertical workspace editor: create an empty workspace draft, add several projects, then edit each project's name, mount as-is/worktree mode and individual branch. Up/Down and Enter expose every action. **Save changes** validates the whole draft, creates worktrees and writes JSON; Escape returns to the list, where closing can discard the draft. Sync is separate unless explicitly requested with `--sync`. Non-interactive `--yes --dir ... --select ... [--branch ...]` remains available. |
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
| `orcan build [--agent NAME [...] \| --all-agents] [--force] [--no-cache] [--prune] [--remove-previous]` | Build `orcan:latest` + `orcan:<VERSION>` with explicit clients. `--prune` removes dangling Orcan images. `--remove-previous` asks `[y/n]` before removing previous local `orcan` tags/images after success; images used by containers are kept. Neither option deletes containers, sandbox data, workspaces, or BuildKit cache. Never publishes. |
| `orcan status` | Product version, installation (`ORCAN_ROOT`), configuration home (`ORCAN_HOME`), data (`ORCAN_DATA`), config file, runtime summary, and the image agent manifest |
| `orcan pull` | Pull portable all-agents `orcan:<VERSION>` → `orcan:latest` |
| `orcan publish` | Push an all-agents `orcan:latest` (**manual**; partial images are refused) |
| `orcan url` | Print browser terminal URL (requires `orcan up --web-terminal`) |
| `orcan enter` / `orcan go-in` | Local terminal into the running container (`--launcher` default, `--shell`, `--tmux [SESSION]`) |
| `orcan attach WORKSPACE` | Create or resume one configured workspace's tmux session and attach the current terminal. For a remote native terminal: `ssh -tt HOST 'orcan attach WORKSPACE'` |
| `orcan update` | Dev channel: fast-forward this checkout to `origin/main` |
| `orcan upgrade [--to VERSION]` | Release channel: newest release tag `vX.Y.Z` (default), or `--to` pins one (up or down) |
| `orcan downgrade [--to VERSION]` | Previous SemVer release, or pin an older `--to` (refuses newer targets) |
| `orcan uninstall [--cli-only] [--purge-data] [--purge-images]` | Stop/remove Orcan runtime and CLI. `--cli-only` keeps containers, images and data; it cannot be combined with purge flags. Data/images are opt-in; `ORCAN_PROJECTS_ROOT` and configured projects are preserved |
| `orcan version` / `orcan help` | Version / help |

### Optional

| Command | Role |
| --- | --- |
| `orcan seed [--all] [--dry-run]` | Copy ignore/templates into git checkouts — **rarely needed**; the workspace context pack is enough |
| `orcan compact [--check]` | Report workspace brief size and revision hash; see [Brief compaction](#brief-compaction) |
| `orcan actions` | Experimental offline action recognition and confirmed scripts; see [Offline actions](../guides/offline-actions.md) |

## Brief compaction

A session brief keeps the current goal and handoff state in
`.orcan/session-brief.md`. Old progress reports can make each new agent read
more than it needs. Orcan recommends a brief within **800 words and 8000 UTF-8
bytes**. These are size limits, not a model token count.

Run `orcan compact` on the host, or `orcan-compact` inside the container.
Both accept the same options and return a small JSON result. They use the
explicit `--workspace PATH`, then `$ORCAN_WORKSPACE_ROOT`, then the nearest
parent with `.manifest.json`. Checks do not change files.

```bash
orcan compact --check --workspace /absolute/path/to/workspace
```

Generated workspace instructions ask the active agent to check at task start
and milestone handoff. If `needs_compact` is true, the agent writes
`.orcan/session-brief.next.md`, preserving the current goal, constraints,
decisions, verified state, open issues, and next steps. Completed history can
move out of the active brief. The agent then applies the candidate with the
`sha256` returned by the check:

```bash
orcan compact --apply .orcan/session-brief.next.md --expected-sha256 HASH
```

The candidate must be non-empty, smaller than the original, and within both
limits. Orcan archives the exact original in `.orcan/brief-history/` before
replacing it. A stale hash refuses the write; the agent must reread and prepare
a fresh summary. Compaction commands serialize their writes. Other editors
should avoid editing the brief during an apply. No archive is deleted automatically.

The active agent writes the summary; Orcan does not call a model or require an
API key. This is instruction-driven upkeep, not a background job or a guarantee
that every agent will follow the request. Archives are read only when historical
detail is needed. The candidate can be removed after a successful apply.
Compaction does not clear the agent's open conversation history.

The host command needs an updated CLI; the container helper needs a rebuilt
image. Updated generated instructions reach existing workspaces on reconcile
(for example, `orcan sync`). Existing briefs are preserved.

## Ritual

```bash
orcan init
orcan settings        # select agents and plugins
orcan sync            # use your ownership exclusions
orcan build           # when preparing/changing image contents
orcan up --plan       # optional read-only preview
orcan up              # local — orcan enter on the same machine
# remote browser: orcan up --web-terminal
```

After config edits:

```bash
# edit ~/.config/orcan/orcan.config.json
orcan sync            # saved ownership exclusions apply
orcan build           # only if image inputs changed
orcan up --plan
orcan up
```

`orcan sync` prepares runtime JSON and mounts, reconciles workspace metadata,
and performs ownership repair subject to saved exclusions. Keep using
`--no-chown PATTERN` / `--chown-exclude PATH` when setting those exclusions;
they are saved in JSON for later explicit synchronizations.

`orcan build` prepares the image. It reuses a completed build when its source,
profile and image ID still match. Use `--force` or `--no-cache` deliberately.
It does not synchronize workspaces.

`orcan up` checks the prepared files, validates Compose, starts the existing local
image and verifies readiness. Missing/stale generated files fail with an explicit
`orcan sync` instruction. An unavailable image fails with an explicit
`orcan build` / `orcan pull` instruction. It does not generate project manifests,
reconcile host workspaces, repair ownership, build or pull images. Startup plugin
hooks still prepare launch overlays and authentication needed for the selected
integrations. Plugin recreate retries also disable building and pulling.
The container entrypoint checks only top-level writable runtime directories;
it no longer scans their contents or recursively changes owners. Repair bind
mount permissions through explicit host sync with exclusions; custom Docker
named volumes require separate explicit maintenance.

Compose convergence keeps an unchanged instance running; changed container
settings or image IDs can recreate it and interrupt attached sessions. Finish
active jobs before applying those changes. `orcan status` records the latest
startup stage: `preflight`, `start`, `verify`, `ready`. A non-ready stage identifies
where that attempt stopped, not the health of an older running instance.

### Build storage check

`orcan build --check-space` reports source filesystem capacity, Docker image and
container usage, reclaimable estimates, and the selected builder's cache totals.
It needs no agent selection or generated configuration. It does not build, pull,
start containers, prune cache or remove anything.

An actual `orcan build` runs the same check after confirming that an image rebuild
is needed. `orcan up` never builds an image and does not run the build storage
check. Reusing an already completed build skips it. `build --plan` remains a configuration-only
preview and makes no Docker calls.

Less than 2 GiB available on a recognized local Docker filesystem produces a
warning and **continues** the build. This threshold is not a build-size estimate;
large selections can require much more. Low source-disk space is reported
separately. `--force` controls image reuse, not storage measurement. An unreachable
Docker daemon stops the attempt because a build cannot run without it.

Orcan measures Docker Root Dir only for a native Linux Docker daemon recognized
on the same host, using a local Unix socket and the default Docker builder for
that context. In containers, Docker Desktop, remote contexts, custom builders,
or inaccessible daemon directories, it reports free space as **unknown**. It
never substitutes source-disk capacity for daemon capacity. Other containerd
filesystems and free inodes are not checked. Image/cache usage can overlap, and
Docker's reclaimable figures do not promise an equivalent amount of freed space.
Inspect storage before deciding whether to clean anything; this command performs
no cleanup and does not inspect or print credentials. Docker CLI uses its normal
connection configuration.

### `orcan up` flags

| Flag | Effect |
| --- | --- |
| *(none)* | Local-only container — no published ttyd port; use `orcan enter` |
| `--web-terminal` \| `--web-terminal-auth USER:PASS` | **Pick one.** `--web-terminal`: browser terminal, no password. `--web-terminal-auth USER:PASS`: same browser terminal **with** HTTP basic auth. Do not pass both. (`TTYD_BIND` defaults to `0.0.0.0`.) |
| `--docker-socket` \| `--network NAME` | **Pick one.** `--docker-socket`: mount `/var/run/docker.sock` (Docker-from-Docker). `--network NAME`: join an existing Docker network (no socket) |
| `--resume` | Restart with the flags of the last `orcan up` (kept across `orcan down`, stored in `mounts/last-up.json`, never the ttyd password). A previous `--web-terminal-auth` start must pass `--web-terminal-auth USER:PASS` again. Orcan Studio Start/Restart use this. |
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

Git identity is synced by `orcan sync` from host `user.name` / `user.email` and applied as container Git defaults on startup. Repository settings can override it. SSH keys are only attached with `--ssh`. Optional flags print a security warning — agents inside can use the mounted socket or keys. Capability ladder and mount tradeoffs: [Security](security.md), [Workflows](../guides/workflows.md).

## Maintainer Make

From a git checkout: `make validate`, `make test-host`, `make docs*`, `make release*`, `make registry-*`. See [Development](../development/overview.md).

Claude executor delivery uses only `submit --notify-tmux` from a registered
`claude-tmux` / `claude-tmux-yolo` process. Confirm consumption with
`ack JOB --tmux-instance "$ORCAN_AGENT_INSTANCE_ID"`. See
[Claude terminal delivery](../guides/background-executor.md#deliver-compact-results-to-a-claude-code-session).

## Plugin defaults

`orcan settings` contains a grouped list of startup plugins and their fields.
`orcan up` starts the saved selection; existing flags and `--with NAME` /
`--without NAME` override one start. See [Startup plugins](../guides/plugins.md)
for package rules, credential sources and compatibility.

## Read-only startup plan

`orcan up --plan [--json]` previews configured image contents, enabled plugins,
ports, managed/project/plugin mounts and required startup checks. Existing
selection flags can be included. It does not create files, inspect Docker or
resolve credentials. See [Settings TUI and startup plan](../guides/settings.md).
