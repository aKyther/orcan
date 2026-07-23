# Docker i Compose

Użyj tej strony dla tagów obrazu, nakładek Compose i bindów `$ORCAN_DATA`. **Dlaczego** jest podział: [Architektura](../architecture.md).

## Obraz

- Baza: Debian Bookworm Slim
- Multi-stage pobieranie narzędzi (Node, Go, Rust, uv)
- Użytkownik nie-root `developer`
- Wejście: `docker-entrypoint`
- Warianty przez build-arg `INSTALL_CURSOR` oraz plik `/etc/orcan/variant`

| Tag | Build | Zawartość |
| --- | --- | --- |
| `orcan:latest` (+ `orcan:full`) | `make build` | Claude + Cursor |
| `orcan:claude` | `make build-claude` | Tylko Claude |

Etykieta wersji: `ORCAN_VERSION` / `/etc/orcan/version`.

## Pliki Compose

| Plik | Rola |
| --- | --- |
| `docker-compose.yml` | Bazowy serwis, bindy `$ORCAN_DATA`, bez socketa Dockera |
| `docker-compose.docker.yml` | Socket Dockera hosta + `DOCKER_GID` |
| `docker-compose.ttyd.yml` | `cursor-ttyd`, opublikowany port, healthcheck |
| `.orcan/compose-projects.generated.yml` | Mounty projektów path-parity (generowane) |

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

CI **nie** publikuje obrazów. Dla własnego rejestru zobacz [Makefile — opcjonalny prywatny rejestr](makefile.md#opcjonalny-prywatny-rejestr).

## Zobacz też

- [Referencja Makefile](makefile.md)
- [Path parity](../concepts/path-parity.md)
- [Bezpieczeństwo](security.md)
- [Wdrożenie](../deployment.md)
