# Environment variables

Use this page when debugging `.env` or Compose. Prefer editing `orcan.config.json` for new setups, then `orcan sync`. Do not commit `.env`.

## Always managed by `orcan sync`

| Variable | Role |
| --- | --- |
| `USER_UID` / `USER_GID` | Map container user to host |
| `DOCKER_GID` | Group for Docker socket (`orcan up --docker-socket`) |
| `TZ` | Timezone |
| `PROJECT_DIR` | Orcan install path (where you run `orcan`) |
| `CONTAINER_PROJECT_DIR` / `WORKSPACE_*` | Primary workspace paths |
| `ORCAN_CONFIG_HOST` / `ORCAN_CONFIG` | Runtime config mount |
| `ORCAN_COMPOSE_PROJECTS` | Generated Compose overlay (project mounts) |
| `ORCAN_DATA` | Host data root (default `$HOME/.config/orcan`) — includes `dotfiles/` for personal shell/tmux/vim overlays |
| `ORCAN_PROJECTS_ROOT` | Stable host root mounted for managed checkouts (default `$ORCAN_DATA/sandbox`) |
| `GIT_AUTHOR_NAME` / `GIT_AUTHOR_EMAIL` | Host `git config --global` identity, mapped to container `ORCAN_GIT_USER_*` defaults |
| `GIT_COMMITTER_NAME` / `GIT_COMMITTER_EMAIL` | Legacy generated values; not forwarded to the container |

## Seeded once (kept on later `orcan sync`)

| Variable | Role |
| --- | --- |
| `CPUS` / `MEMORY` / `SHM_SIZE` / `TMPFS_SIZE` | Resource limits (defaults: 2 / 4g / 512m / 512m) |
| `TTYD_PORT` / `TTYD_HOST_PORT` / `TTYD_BIND` / `TTYD_FONT_*` / `TTYD_RENDERER` / `TTYD_THEME` / `TTYD_PING_INTERVAL` | Browser terminal (`TTYD_RENDERER`: `webgl` by default, `canvas` fallback; `TTYD_BIND` default `0.0.0.0`; `TTYD_THEME`: `dark`/`navy`, `mocha`, or raw xterm.js JSON) |
| `TTYD_CREDENTIAL` | Optional ttyd HTTP basic auth (`user:password`). Set only in `.env` — never commit |

## Compose naming (optional)

| Variable | Role |
| --- | --- |
| `COMPOSE_PROJECT_NAME` | Compose project (CLI default `orcan`) |
| `ORCAN_INSTANCE` | Container name suffix → `orcan-1`, `orcan-2`, … (default `1`) |

Edit via `orcan.config.json` (`resources`, `ttyd`) then `orcan sync` for new machines; existing `.env` values may be preserved depending on `update-env.sh` rules — prefer config file as source of truth for new setups.

### `ORCAN_PROJECTS_ROOT` safety and edge cases

`orcan sync` writes the resolved value to `$ORCAN_HOME/.env`. With no override:

```text
ORCAN_DATA=$HOME/.config/orcan
ORCAN_PROJECTS_ROOT=$ORCAN_DATA/sandbox
```

The nested default gives Docker one stable bind mount and lets Orcan add managed
worktrees without recreating the container. It also means project checkouts are
physically below the data directory. `orcan uninstall --purge-data` therefore
uses a selective purge: it preserves the complete `ORCAN_PROJECTS_ROOT` tree and
every project path still listed in `orcan.config.json`.

You may instead use an external root such as `/home/me/Projects/orcan`. Set it
before `orcan sync`; it must be an absolute host path. Important edge cases:

- Changing `.env` does **not** move existing repositories or rewrite project
  paths in `orcan.config.json`. Move them and update the JSON paths first, then
  run `orcan sync`.
- If `ORCAN_PROJECTS_ROOT` equals `ORCAN_DATA`, a safe data purge keeps that
  whole directory because data and projects cannot be separated.
- A symlink *inside* `ORCAN_DATA` used as `ORCAN_PROJECTS_ROOT` is preserved
  without following it during deletion. A symlink used as `ORCAN_DATA` or
  `ORCAN_HOME` is rejected by purge; point the variable at its real directory.
- Multiple Orcan setups sharing one projects root are safe from uninstall, but
  changing or deleting repositories still affects every setup that references
  them.
- Repositories neither below `ORCAN_PROJECTS_ROOT` nor present in the current
  `orcan.config.json` are ordinary files as far as purge is concerned. Do not
  store unregistered repositories under `ORCAN_DATA`.

## Image selection

| Variable | Role |
| --- | --- |
| `IMAGE_LOCAL` | Image Compose runs (default `orcan:latest`) |
| `INSTALL_CURSOR` / `INSTALL_CLAUDE` | Build-args (`1`/`0`); default both on |
| `ORCAN_VERSION` | Build-arg from `cockpit/pyproject.toml` (mirrored in root `VERSION`) |

## Optional private registry

| Variable | Role |
| --- | --- |
| `IMAGE_REGISTRY` / `IMAGE_REPOSITORY` / `IMAGE_TAG` | `orcan publish` / `orcan pull` |

## Inside the container

| Variable | Role |
| --- | --- |
| `ORCAN_VERSION` | From `/etc/orcan/version` |
| `HISTFILE` | Default `~/.local/share/orcan/history/.zsh_history`; in tmux, per workspace: `…/history/workspaces/<name>/.zsh_history` (bind: `$ORCAN_DATA/history`) |
| `npm_config_cache` / `PNPM_HOME` / `CARGO_HOME` / `GOPATH` | Under `~/.cache/…` (bind: `$ORCAN_DATA/cache`) |
| `ORCAN_GIT_USER_NAME` / `ORCAN_GIT_USER_EMAIL` | Host identity applied to global Git config on startup; repository config can override it |
| `SSH_AUTH_SOCK` | Host agent (only with `orcan up --ssh`) |
| `ORCAN_SUPERVISOR_MODE` | Set by Compose overlays: `keepalive` (default `orcan up`) or `ttyd` (`--web-terminal`) — see [Docker](docker.md#process-layout-supervisord) |

### Devtool cache hygiene

Login shells and `docker-entrypoint` (so `agent` / `claude` inherit the same env) set:

| Variable | Effect |
| --- | --- |
| `PYTHONDONTWRITEBYTECODE=1` | No `__pycache__` / `.pyc` next to sources |
| `PYTHONUNBUFFERED=1` | Unbuffered Python stdout/stderr |
| `RUFF_CACHE_DIR` / `MYPY_CACHE_DIR` / `PIP_CACHE_DIR` / `UV_CACHE_DIR` / `PRE_COMMIT_HOME` / … | Caches under `$HOME/.cache` (host: `$ORCAN_DATA/cache`) |
| `PYTEST_ADDOPTS` includes `-p no:cacheprovider` | No `.pytest_cache/` in repos |

Override any of these in the environment if a tool must use its default on-disk layout. Seeded ignore templates also list common cache dirs so agents skip them if they appear.

See also `.env.example`.

## Optional GitHub access

`orcan up --github [--github-hostname HOST]` reads host authentication only when
requested. `GH_TOKEN` takes precedence over `GITHUB_TOKEN` for `github.com` and
`*.ghe.com`. `GH_ENTERPRISE_TOKEN` takes precedence over `GITHUB_ENTERPRISE_TOKEN`
for a GitHub Enterprise Server hostname. A saved `gh auth login` for the selected
host is the fallback. The container receives `GH_HOST` and the selected token
variable; the other token variables are cleared. `ORCAN_GITHUB_TOKEN` is an
internal, temporary Compose interpolation variable, not a persisted setting.
See [GitHub access](cli.md#github-access) for examples and token visibility.

## Optional GitLab access

`orcan up --gitlab [--gitlab-hostname HOST]` defaults to `gitlab.com`.
`GITLAB_TOKEN` takes precedence over `GITLAB_ACCESS_TOKEN`, then `OAUTH_TOKEN`.
The saved `glab` login for the exact hostname is the fallback. The container
receives `GITLAB_HOST` and `GITLAB_TOKEN`; alternative token variables and
`CI_JOB_TOKEN` are cleared, and `GLAB_ENABLE_CI_AUTOLOGIN` is disabled for this
access mode. `ORCAN_GITLAB_TOKEN` is internal and temporary, not persisted.
See [GitLab access](cli.md#gitlab-access).
