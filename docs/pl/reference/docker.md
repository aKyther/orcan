# Docker i Compose

Użyj tej strony dla tagów obrazu, nakładek Compose i bindów `$ORCAN_DATA`. **Dlaczego** jest podział: [Architektura](../architecture.md).

## Obraz

- Baza: Debian Bookworm Slim
- Multi-stage pobieranie narzędzi (Node, Go, Rust, uv)
- tmux **3.6a** z `tmux/tmux-builds` (nie pakiet bookworm 3.3a)
- Użytkownik nie-root `developer`
- Wejście: `docker-entrypoint`

| Tag | Rola |
| --- | --- |
| `orcan:latest` | Obaj agenci — to, co Compose uruchamia domyślnie |
| `orcan:<VERSION>` | Ten sam obraz (rejestr + lokalny pin) |
| `orcan:<VERSION>-claude` | Tylko lokalnie — Claude Code, bez Cursor |
| `orcan:<VERSION>-cursor` | Tylko lokalnie — Cursor CLI, bez Claude |

Wybór agenta:

| Flaga | Efekt |
| --- | --- |
| (brak) | Pull `orcan:<VERSION>` jeśli jest, inaczej build obu → `latest` + `<VERSION>` |
| `--claude` | Bez pull; build `orcan:<VERSION>-claude` (nie rusza `latest`) |
| `--cursor` | Bez pull; build `orcan:<VERSION>-cursor` |

Potem: `IMAGE_LOCAL=orcan:<VERSION>-claude orcan up` (albo `IMAGE_LOCAL` w `.env`). `/etc/orcan/variant`: `full` / `claude` / `cursor`. `orcan publish` pcha tylko tagi z oboma agentami.

Build-argi: `INSTALL_CLAUDE` / `INSTALL_CURSOR` (domyślnie oba `1`).
Etykieta wersji: `ORCAN_VERSION` / `/etc/orcan/version`.

## Pliki Compose

| Plik | Rola |
| --- | --- |
| `docker-compose.yml` | Bazowy serwis, bindy `$ORCAN_DATA`, bez socketa Dockera |
| `docker-compose.docker.yml` | Socket Dockera hosta + `DOCKER_GID` |
| `docker-compose.ttyd.yml` | `cursor-ttyd`, opublikowany port, healthcheck |
| `mounts/compose-projects.generated.yml` | Mounty projektów path-parity (generowane) |

## Bindy `$ORCAN_DATA`

Domyślny root hosta: `~/.config/orcan`.

| Host | Kontener |
| --- | --- |
| `cursor/` | `~/.cursor` |
| `cursor-app/` | `~/.config/cursor` |
| `claude/` | `~/.claude` (`CLAUDE_CONFIG_DIR` — OAuth + settings przeżywają restarty) |
| `cache/`, `npm/`, `pnpm/`, `cargo/`, `go/` | Cache/home narzędzi |
| `shell-history/` | `/command-history` (historia zsh) |

Nazwane wolumeny Dockera **nie** są używane do tych danych.

## Opcjonalny prywatny rejestr

CI **nie** publikuje obrazów. Dla własnego rejestru użyj `orcan pull` / `orcan publish` (zobacz [Referencja CLI](cli.md)). Helpery maintainerów: [Makefile — opcjonalny rejestr](makefile.md#opcjonalny-prywatny-rejestr).

## Zobacz też

- [Referencja Makefile](makefile.md)
- [Path parity](../concepts/path-parity.md)
- [Bezpieczeństwo](security.md)
- [Wdrożenie](../deployment.md)
