# Zmienne środowiskowe

Użyj tej strony przy debugowaniu `.env` lub Compose. Przy nowych setupach preferuj edycję `orcan.config.json`, potem `orcan sync`. Nie commituj `.env`.

## Zawsze zarządzane przez `orcan sync`

| Zmienna | Rola |
| --- | --- |
| `USER_UID` / `USER_GID` | Mapowanie użytkownika kontenera na hosta |
| `DOCKER_GID` | Grupa dla socketa Dockera (`orcan up --with-docker`) |
| `TZ` | Strefa czasowa |
| `PROJECT_DIR` | Ścieżka instalacji Orcana (gdzie uruchamiasz `orcan`) |
| `CONTAINER_PROJECT_DIR` / `WORKSPACE_*` | Ścieżki primary workspace |
| `ORCAN_CONFIG_HOST` / `ORCAN_CONFIG` | Mount runtime config |
| `ORCAN_COMPOSE_PROJECTS` | Wygenerowana nakładka Compose (mounty projektów) |
| `ORCAN_DATA` | Root danych hosta (domyślnie `$HOME/.config/orcan`) — w tym `dotfiles/` na własne aliasy/tmux/vim |
| `GIT_AUTHOR_NAME` / `GIT_AUTHOR_EMAIL` | Tożsamość z hostowego `git config --global` (commity w kontenerze) |
| `GIT_COMMITTER_NAME` / `GIT_COMMITTER_EMAIL` | Jak autor (trzymane w syncu) |

## Seedowane raz (zachowywane przy kolejnym `orcan sync`)

| Zmienna | Rola |
| --- | --- |
| `CPUS` / `MEMORY` / `SHM_SIZE` / `TMPFS_SIZE` | Limity zasobów (domyślnie: 2 / 4g / 512m / 512m) |
| `TTYD_PORT` / `TTYD_HOST_PORT` / `TTYD_BIND` / `TTYD_FONT_*` / `TTYD_THEME` / `TTYD_PING_INTERVAL` | Terminal w przeglądarce (`TTYD_BIND` domyślnie `0.0.0.0`; `TTYD_THEME`: `dark`/`navy`, `mocha` albo surowy JSON xterm.js) |
| `TTYD_CREDENTIAL` | Opcjonalne HTTP basic auth ttyd (`user:password`). Tylko w `.env` — nigdy nie commituj |

## Nazwy Compose (opcjonalne)

| Zmienna | Rola |
| --- | --- |
| `COMPOSE_PROJECT_NAME` | Projekt Compose (CLI domyślnie `orcan`) |
| `ORCAN_INSTANCE` | Sufiks nazwy kontenera → `orcan-1`, `orcan-2`, … (domyślnie `1`) |

Edytuj przez `orcan.config.json` (`resources`, `ttyd`), potem `orcan sync` na nowych maszynach; istniejące wartości `.env` mogą być zachowane zależnie od reguł `update-env.sh` — przy nowych setupach preferuj plik konfiguracji jako źródło prawdy.

## Wybór obrazu

| Zmienna | Rola |
| --- | --- |
| `IMAGE_LOCAL` | Obraz Compose (domyślnie `orcan:latest`) |
| `INSTALL_CURSOR` / `INSTALL_CLAUDE` | Build-argi (`1`/`0`); domyślnie oba włączone |
| `ORCAN_VERSION` | Build-arg z `cockpit/pyproject.toml` (lustro: root `VERSION`) |

## Opcjonalny prywatny rejestr

| Zmienna | Rola |
| --- | --- |
| `IMAGE_REGISTRY` / `IMAGE_REPOSITORY` / `IMAGE_TAG` | `orcan publish` / `orcan pull` |

## Wewnątrz kontenera

| Zmienna | Rola |
| --- | --- |
| `ORCAN_VARIANT` | `full` lub `claude` (z `/etc/orcan/variant`) |
| `ORCAN_VERSION` | Z `/etc/orcan/version` |
| `HISTFILE` | `~/.local/share/orcan/history/.zsh_history` (bind: `$ORCAN_DATA/history`) |
| `npm_config_cache` / `PNPM_HOME` / `CARGO_HOME` / `GOPATH` | Pod `~/.cache/…` (bind: `$ORCAN_DATA/cache`) |
| `GIT_AUTHOR_*` / `GIT_COMMITTER_*` | Ta sama tożsamość commitów co użytkownik hosta |
| `SSH_AUTH_SOCK` | Agent hosta (tylko z `orcan up --with-git`) |
| `ORCAN_SUPERVISOR_MODE` | Ustawiane przez overlaye Compose: `keepalive` (domyślne `orcan up`) albo `ttyd` (`--with-ttyd`) — zobacz [Docker](docker.md#process-layout-supervisord) |
| `ORCAN_CONTEXT_SCAN` | `0` wyłącza worker `orcan-context-scan`; domyślnie włączony |
| `ORCAN_CONTEXT_DRIVER` | `recap` (domyślnie) albo `reflect` (legacy one-shot `orcan-context-reflect`) — patrz [Context Assertions](../ideas/context-assertions.md) |
| `ORCAN_CONTEXT_MODEL_PROBE` | `0` pomija probe `claude -p --model haiku` przy sprawdzaniu modelu recap (tylko PATH + `--version`); domyślnie włączony |

### Higiena cache narzędzi developerskich

Shelly logowania i `docker-entrypoint` (żeby `agent` / `claude` dziedziczyły to samo) ustawiają:

| Zmienna | Efekt |
| --- | --- |
| `PYTHONDONTWRITEBYTECODE=1` | Brak `__pycache__` / `.pyc` obok źródeł |
| `PYTHONUNBUFFERED=1` | Niebuforowane stdout/stderr Pythona |
| `RUFF_CACHE_DIR` / `MYPY_CACHE_DIR` / `PIP_CACHE_DIR` / `UV_CACHE_DIR` / `PRE_COMMIT_HOME` / … | Cache w `$HOME/.cache` (host: `$ORCAN_DATA/cache`) |
| `PYTEST_ADDOPTS` zawiera `-p no:cacheprovider` | Brak `.pytest_cache/` w repozytoriach |

Nadpisz dowolną z tych zmiennych, jeśli narzędzie musi użyć domyślnego układu na dysku. Szablony ignore też listują typowe katalogi cache, żeby agenci je pomijali, gdy już powstaną.

Zobacz też `.env.example`.

## Zobacz też

- [Referencja konfiguracji](configuration.md)
- [Referencja Makefile](makefile.md)
- [Docker](docker.md)
- [Bezpieczeństwo](security.md)
