# Environment variables

Use this page when debugging `.env` or Compose. Prefer editing `orcan.config.json` for new setups, then `make env`. Do not commit `.env`.

## Always managed by `make env`

| Variable | Role |
| --- | --- |
| `USER_UID` / `USER_GID` | Map container user to host |
| `DOCKER_GID` | Group for Docker socket (`terminal-docker`) |
| `TZ` | Timezone |
| `PROJECT_DIR` | Orcan repo path (where you run Make) |
| `CONTAINER_PROJECT_DIR` / `WORKSPACE_*` | Primary workspace paths |
| `ORCAN_CONFIG_HOST` / `ORCAN_CONFIG` | Runtime config mount |
| `ORCAN_COMPOSE_PROJECTS` | Generated Compose overlay |
| `ORCAN_DATA` | Host data root (default `$HOME/.config/orcan`) |

## Seeded once (kept on later `make env`)

| Variable | Role |
| --- | --- |
| `CPUS` / `MEMORY` / `SHM_SIZE` / `TMPFS_SIZE` | Resource limits |
| `TTYD_PORT` / `TTYD_HOST_PORT` / `TTYD_FONT_*` / `TTYD_THEME` | Browser terminal |

Edit via `orcan.config.json` (`resources`, `ttyd`) then `make env` for new machines; existing `.env` values may be preserved depending on `update-env.sh` rules — prefer config file as source of truth for new setups.

## Image selection

| Variable | Role |
| --- | --- |
| `IMAGE_LOCAL` | Image Compose runs (`orcan:latest` or `orcan:claude`) |
| `INSTALL_CURSOR` | Build-arg only (`1` full / `0` Claude-only) |
| `ORCAN_VERSION` | Build-arg from `VERSION` file |

## Optional private registry

| Variable | Role |
| --- | --- |
| `IMAGE_REGISTRY` / `IMAGE_REPOSITORY` / `IMAGE_TAG` | `make publish` / `pull` |

## Inside the container

| Variable | Role |
| --- | --- |
| `ORCAN_VARIANT` | `full` or `claude` (from `/etc/orcan/variant`) |
| `ORCAN_VERSION` | From `/etc/orcan/version` |
| `HISTFILE` | `/command-history/.zsh_history` (bind: `$ORCAN_DATA/shell-history`) |

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
