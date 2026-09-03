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
| `orcan:latest` | Zwykły obraz Orcan uruchamiany przez Compose |
| `orcan:<VERSION>` | Wersjonowany tag tego samego obrazu |

Wybór agenta:

| Flaga | Efekt |
| --- | --- |
| `--agent NAZWA` | Dodaje klienta (`cursor`, `claude`, `codex`, `gemini`, `copilot`) |
| `--all-agents` | Instaluje wszystkich obsługiwanych klientów |

`/etc/orcan/agents.json` zapisuje listę klientów; `orcan status` i `orcan doctor` ją pokazują. Dane Gemini i Copilota trwale leżą w `ORCAN_DATA/gemini` oraz `ORCAN_DATA/copilot`.

Build-argi: `INSTALL_CURSOR` / `INSTALL_CLAUDE` / `INSTALL_CODEX` / `INSTALL_GEMINI` / `INSTALL_COPILOT`.
Etykieta wersji: `ORCAN_VERSION` / `/etc/orcan/version`.

## Pliki Compose

| Plik | Rola |
| --- | --- |
| `docker-compose.yml` | Bazowy serwis, bindy `$ORCAN_DATA`, bez socketa Dockera |
| `docker-compose.keepalive.yml` | `orcan-supervisord` z `ORCAN_SUPERVISOR_MODE=keepalive` — domyślne `orcan up` (lokalnie; `orcan enter`) |
| `docker-compose.docker.yml` | Socket Dockera hosta + `DOCKER_GID` |
| `docker-compose.ttyd.yml` | `orcan-supervisord` z `ORCAN_SUPERVISOR_MODE=ttyd` przy `orcan up --with-ttyd`; opublikowany port (`TTYD_BIND`, domyślnie `0.0.0.0`), opcjonalne `TTYD_CREDENTIAL`, healthcheck |
| `mounts/compose-projects.generated.yml` | Mounty projektów path-parity (generowane) |

Nakładki dla `orcan up --with-ttyd` / `--with-docker` / `--with-git` /
`--with-network` są opt-in. Drabinka możliwości i ryzyka: [Bezpieczeństwo](security.md).

ttyd: domyślna publikacja to wszystkie interfejsy (`TTYD_BIND=0.0.0.0`).
**Rekomendowany dostęp zdalny** to Tailscale (albo inny prywatny VPN) plus
`TTYD_CREDENTIAL` / `--with-ttyd-auth`. `TTYD_BIND=127.0.0.1` tylko lokalnie
na hoście. `orcan url` drukuje `http://localhost:<port>` przy wildcard bind.

## Układ procesów (supervisord) { #process-layout-supervisord }

`orcan up` nie używa już gołego `sleep infinity` / `cursor-ttyd` jako
komendy Compose. Oba overlaye uruchamiają **`orcan-supervisord`**, który
wybiera programy z `/etc/orcan/supervisor.d/` do `/tmp/orcan-supervisor.d/`
i robi `exec supervisord -n`:

| `ORCAN_SUPERVISOR_MODE` | Program „trzymający” kontener | Typowy dostęp |
| --- | --- | --- |
| `keepalive` (domyślny) | `sleep infinity` | `orcan enter` |
| `ttyd` | `cursor-ttyd` | przeglądarka |

| Program | Komenda |
| --- | --- |

**Logi** (trwałe na bindzie history — przeżywają recreate):

| Ścieżka (kontener) | Host |
| --- | --- |
| `~/.local/share/orcan/history/supervisor/` | `$ORCAN_DATA/history/supervisor/` |

| Plik | Co |
| --- | --- |
| `supervisord.log` | Supervisor + banner startu |
| `childlog/ttyd.*.log` | Terminal przeglądarkowy (tryb ttyd) |

## Bindy `$ORCAN_DATA`

Domyślny root hosta: `~/.config/orcan`.

| Host | Kontener |
| --- | --- |
| `cursor/` | `~/.cursor` |
| `cursor-app/` | `~/.config/cursor` |
| `claude/` | `~/.claude` (`CLAUDE_CONFIG_DIR` — OAuth + settings przeżywają restarty) |
| `codex/` | `~/.codex` |
| `cache/` | `~/.cache` (npm / pnpm / cargo / go / uv / … gniazdują tu przez env) |
| `history/` | `~/.local/share/orcan/history` (`HISTFILE`) |
| `dotfiles/` | `~/.config/orcan/dotfiles` |

W kontenerze `~/orcan-map/` to mapa symlinków (agents, cache, history, dotfiles,
workspaces), żeby łatwo ogarnąć drzewo sandboxa. Narzędzia nadal używają
swoich normalnych home (`~/.cursor`, …).

Nazwane wolumeny Dockera **nie** są używane do tych danych.

Upgrade ze starszego layoutu `$ORCAN_DATA` (płaskie `npm/` / `shell-history/`
albo zagnieżdżone `cache/cache/`): na hoście uruchom
`bash scripts/migrations/consolidate-container-data.sh` przed
`orcan sync && orcan up`.

## Opcjonalny prywatny rejestr

CI **nie** publikuje obrazów. Dla własnego rejestru użyj `orcan pull` / `orcan publish` (zobacz [Referencja CLI](cli.md)). Helpery maintainerów: [Makefile — opcjonalny rejestr](makefile.md#opcjonalny-prywatny-rejestr).

## Zobacz też

- [Referencja Makefile](makefile.md)
- [Path parity](../concepts/path-parity.md)
- [Bezpieczeństwo](security.md)
- [Wdrożenie](../deployment.md)
