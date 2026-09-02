# Environment variables

Use this page when debugging `.env` or Compose. Prefer editing `orcan.config.json` for new setups, then `orcan sync`. Do not commit `.env`.

## Always managed by `orcan sync`

| Variable | Role |
| --- | --- |
| `USER_UID` / `USER_GID` | Map container user to host |
| `DOCKER_GID` | Group for Docker socket (`orcan up --with-docker`) |
| `TZ` | Timezone |
| `PROJECT_DIR` | Orcan install path (where you run `orcan`) |
| `CONTAINER_PROJECT_DIR` / `WORKSPACE_*` | Primary workspace paths |
| `ORCAN_CONFIG_HOST` / `ORCAN_CONFIG` | Runtime config mount |
| `ORCAN_COMPOSE_PROJECTS` | Generated Compose overlay (project mounts) |
| `ORCAN_DATA` | Host data root (default `$HOME/.config/orcan`) — includes `dotfiles/` for personal shell/tmux/vim overlays |
| `ORCAN_PROJECTS_ROOT` | Stable host root mounted for managed checkouts (default `$ORCAN_DATA/sandbox`) |
| `GIT_AUTHOR_NAME` / `GIT_AUTHOR_EMAIL` | Host `git config --global` identity for in-container commits |
| `GIT_COMMITTER_NAME` / `GIT_COMMITTER_EMAIL` | Same as author (kept in sync) |

## Seeded once (kept on later `orcan sync`)

| Variable | Role |
| --- | --- |
| `CPUS` / `MEMORY` / `SHM_SIZE` / `TMPFS_SIZE` | Resource limits (defaults: 2 / 4g / 512m / 512m) |
| `TTYD_PORT` / `TTYD_HOST_PORT` / `TTYD_BIND` / `TTYD_FONT_*` / `TTYD_THEME` / `TTYD_PING_INTERVAL` | Browser terminal (`TTYD_BIND` default `0.0.0.0`; `TTYD_THEME`: `dark`/`navy`, `mocha`, or raw xterm.js JSON) |
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
| `ORCAN_VARIANT` | `full` or `claude` (from `/etc/orcan/variant`) |
| `ORCAN_VERSION` | From `/etc/orcan/version` |
| `HISTFILE` | Default `~/.local/share/orcan/history/.zsh_history`; in tmux, per workspace: `…/history/workspaces/<name>/.zsh_history` (bind: `$ORCAN_DATA/history`) |
| `npm_config_cache` / `PNPM_HOME` / `CARGO_HOME` / `GOPATH` | Under `~/.cache/…` (bind: `$ORCAN_DATA/cache`) |
| `GIT_AUTHOR_*` / `GIT_COMMITTER_*` | Same commit identity as the host user |
| `SSH_AUTH_SOCK` | Host agent (only with `orcan up --with-git`) |
| `ORCAN_SUPERVISOR_MODE` | Set by Compose overlays: `keepalive` (default `orcan up`) or `ttyd` (`--with-ttyd`) — see [Docker](docker.md#process-layout-supervisord) |
| `ORCAN_CONTEXT_SCAN` | `0` skips the background `orcan-context-scan` worker; default on |
| `ORCAN_CONTEXT_DRIVER` | `recap` (default) or `reflect` (legacy one-shot `orcan-context-reflect` path) — see [Context Assertions](../ideas/context-assertions.md) |
| `ORCAN_CONTEXT_MODEL_PROBE` | `0` skips the live `claude -p --model haiku` probe in recap model checks (PATH + `--version` only); default on |

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
