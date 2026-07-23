# Zmienne środowiskowe

Użyj tej strony przy debugowaniu `.env` lub Compose. Przy nowych setupach preferuj edycję `orcan.config.json`, potem `make env`. Nie commituj `.env`.

## Zawsze zarządzane przez `make env`

| Zmienna | Rola |
| --- | --- |
| `USER_UID` / `USER_GID` | Mapowanie użytkownika kontenera na hosta |
| `DOCKER_GID` | Grupa dla socketa Dockera (`terminal-docker`) |
| `TZ` | Strefa czasowa |
| `PROJECT_DIR` | Ścieżka repo Orcana (gdzie uruchamiasz Make) |
| `CONTAINER_PROJECT_DIR` / `WORKSPACE_*` | Ścieżki primary workspace |
| `ORCAN_CONFIG_HOST` / `ORCAN_CONFIG` | Mount runtime config |
| `ORCAN_COMPOSE_PROJECTS` | Wygenerowana nakładka Compose |
| `ORCAN_DATA` | Root danych hosta (domyślnie `$HOME/.config/orcan`) |

## Seedowane raz (zachowywane przy kolejnym `make env`)

| Zmienna | Rola |
| --- | --- |
| `CPUS` / `MEMORY` / `SHM_SIZE` / `TMPFS_SIZE` | Limity zasobów |
| `TTYD_PORT` / `TTYD_HOST_PORT` / `TTYD_FONT_*` / `TTYD_THEME` | Terminal w przeglądarce |

Edytuj przez `orcan.config.json` (`resources`, `ttyd`), potem `make env` na nowych maszynach; istniejące wartości `.env` mogą być zachowane zależnie od reguł `update-env.sh` — przy nowych setupach preferuj plik konfiguracji jako źródło prawdy.

## Wybór obrazu

| Zmienna | Rola |
| --- | --- |
| `IMAGE_LOCAL` | Obraz uruchamiany przez Compose (`orcan:latest` lub `orcan:claude`) |
| `INSTALL_CURSOR` | Tylko build-arg (`1` pełny / `0` tylko Claude) |
| `ORCAN_VERSION` | Build-arg z pliku `VERSION` |

## Opcjonalny prywatny rejestr

| Zmienna | Rola |
| --- | --- |
| `IMAGE_REGISTRY` / `IMAGE_REPOSITORY` / `IMAGE_TAG` | `make publish` / `pull` |

## Wewnątrz kontenera

| Zmienna | Rola |
| --- | --- |
| `ORCAN_VARIANT` | `full` lub `claude` (z `/etc/orcan/variant`) |
| `ORCAN_VERSION` | Z `/etc/orcan/version` |
| `HISTFILE` | `/command-history/.zsh_history` (bind: `$ORCAN_DATA/shell-history`) |

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
