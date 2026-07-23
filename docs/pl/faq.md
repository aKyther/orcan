---
description: Krótkie odpowiedzi o Orcanie — modele, obrazy, aktualizacja, odinstalowanie, błędy i contributing.
---

# FAQ

Krótkie odpowiedzi na częste pytania o Orcana.

## Czym jest Orcan?

Orcan to **orkiestrator kontekstu pracy**. Uruchamia Cursor CLI (`agent`) i Claude Code (`claude`) w Dockerze z workspace'ami (nazwanymi zbiorami projektów), montowaniem path-parity oraz terminalem w przeglądarce.

Zanim przejdziesz dalej w FAQ, przeczytaj [Dlaczego Orcan?](why-orcan.md) oraz [Idee podstawowe](ideas/core-ideas.md).

## Czy Orcan wybiera modele AI?

**Nie.** Modele pozostają przy każdym CLI / koncie. Orcan nie przypina ani nie routuje modeli.

## Jak przełączyć projekty?

Edytuj `orcan.config.json` (lub `make config-wizard`), potem:

```bash
make env
make down && make terminal-docker
```

**Nie** przekazuj `PROJECT_DIR=…` do `make terminal*`.

## Dlaczego `make terminal` ignoruje zmiany w konfiguracji?

`make terminal*` nie uruchamia `make env`. Najpierw zawsze zastosuj konfigurację.

## Pełny obraz vs tylko Claude?

=== "Pełny (domyślny)"

    ```bash
    make build
    make terminal-docker
    ```

    Obraz: `orcan:latest` — Claude + Cursor (`agent`).

=== "Tylko Claude"

    ```bash
    make build-claude
    IMAGE_LOCAL=orcan:claude make terminal-docker
    ```

    Obraz: `orcan:claude` — tylko Claude (`agent` nie jest zainstalowany).

## Czy jest opublikowany obraz Docker?

**Nie** (nie z CI). Sklonuj repozytorium i uruchom `make build`. Opcjonalne helpery prywatnego rejestru istnieją do zaawansowanego użycia.

## Gdzie są dane logowania / cache?

Pod `$ORCAN_DATA` (domyślnie `~/.config/orcan`):

| Ścieżka na hoście | Co |
| --- | --- |
| `claude/` | Konfiguracja Claude Code + OAuth (`.credentials.json`, settings). `CLAUDE_CONFIG_DIR` wskazuje tu, żeby login przeżywał restarty |
| `cursor/` | Home CLI Cursor |
| `cache/` | Cache narzędzi (ruff, pip, uv, …) |

Po `make rebuild` / restarcie **nie** powinieneś musieć ponownie robić `/login`, chyba że wyczyściłeś `$ORCAN_DATA` albo nigdy nie dokończyłeś logowania przy zamontowanym volume.

## Czy mogę wyłączyć tmux?

Nie jako obsługiwany przełącznik. Launcher startuje tmux. Zamiast tego używaj wielu okien/paneli tmux.

## Jak zaktualizować?

```bash
git fetch && git checkout vX.Y.Z   # albo: main
make env                           # gdy zmienił się schemat konfiguracji
make rebuild                       # gdy zmienił się Dockerfile/rootfs
make down && make terminal-docker
```

## Jak odinstalować? { #uninstall }

```bash
cd /absolute/path/to/orcan
make down
make clean-data          # destrukcyjne: usuwa ~/.config/orcan (wpisz yes)
docker images 'orcan*'   # opcjonalnie: docker rmi …
# potem usuń katalog clone'a, jeśli go nie potrzebujesz
```

Szczegóły: [Workflowy — odinstalowanie](guides/workflows.md#odinstalowanie).

## Jak zgłosić błąd?

Otwórz Issue na GitHubie: system, wersja Dockera, target Make oraz logi (`make logs`, `make path-check`):

https://github.com/aKyther/orcan/issues

## Jak dołożyć własny kod / contribute?

1. Przeczytaj [Contributing](https://github.com/aKyther/orcan/blob/main/CONTRIBUTING.md).
2. Zobacz [Przegląd rozwoju](development/overview.md).
3. Otwórz PR do `main`.

## Zobacz też

- [Szybki start](getting-started/quickstart.md)
- [Rozwiązywanie problemów](guides/troubleshooting.md)
- [Konfiguracja](getting-started/configuration.md)
- [Issues na GitHubie](https://github.com/aKyther/orcan/issues)
