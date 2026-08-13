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
| `GIT_AUTHOR_NAME` / `GIT_AUTHOR_EMAIL` | Host `git config --global` identity for in-container commits |
| `GIT_COMMITTER_NAME` / `GIT_COMMITTER_EMAIL` | Same as author (kept in sync) |

## Seeded once (kept on later `orcan sync`)

| Variable | Role |
| --- | --- |
| `CPUS` / `MEMORY` / `SHM_SIZE` / `TMPFS_SIZE` | Resource limits (defaults: 2 / 4g / 512m / 512m) |
| `TTYD_PORT` / `TTYD_HOST_PORT` / `TTYD_FONT_*` / `TTYD_THEME` / `TTYD_PING_INTERVAL` | Browser terminal (`TTYD_THEME`: `dark`/`navy`, `mocha`, or raw xterm.js JSON) |

## Compose naming (optional)

| Variable | Role |
| --- | --- |
| `COMPOSE_PROJECT_NAME` | Compose project (CLI default `orcan`) |
| `ORCAN_INSTANCE` | Container name suffix → `orcan-1`, `orcan-2`, … (default `1`) |

Edit via `orcan.config.json` (`resources`, `ttyd`) then `orcan sync` for new machines; existing `.env` values may be preserved depending on `update-env.sh` rules — prefer config file as source of truth for new setups.

## Image selection

| Variable | Role |
| --- | --- |
| `IMAGE_LOCAL` | Image Compose runs (default `orcan:latest`) |
| `INSTALL_CURSOR` / `INSTALL_CLAUDE` | Build-args (`1`/`0`); default both on |
| `ORCAN_VERSION` | Build-arg from `VERSION` file |

## Optional private registry

| Variable | Role |
| --- | --- |
| `IMAGE_REGISTRY` / `IMAGE_REPOSITORY` / `IMAGE_TAG` | `orcan publish` / `orcan pull` |

## Inside the container

| Variable | Role |
| --- | --- |
| `ORCAN_VARIANT` | `full` or `claude` (from `/etc/orcan/variant`) |
| `ORCAN_VERSION` | From `/etc/orcan/version` |
| `HISTFILE` | `/command-history/.zsh_history` (bind: `$ORCAN_DATA/shell-history`) |
| `GIT_AUTHOR_*` / `GIT_COMMITTER_*` | Same commit identity as the host user |
| `SSH_AUTH_SOCK` | Host agent (only with `orcan up --with-git`) |

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
