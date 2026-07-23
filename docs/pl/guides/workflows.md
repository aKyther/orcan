# Typowe workflowy

Wszystkie polecenia poniżej uruchamiasz na **hoście**, o ile nie oznaczono **(kontener)**.

## Codzienny start

```bash
cd /absolute/path/to/orcan
make terminal-docker
```

Otwórz `http://localhost:7681`. To **nie** uruchamia `make env`.

!!! note
    Po każdej edycji `orcan.config.json`: `make env`, potem `make down && make terminal-docker` (opcjonalnie najpierw `make init-project-all`).

## Zmiana workspace'ów lub portów

```bash
make config-wizard    # albo edytuj orcan.config.json
make env
make init-project-all
make down
make terminal-docker
```

## Uruchomienie bez socketa Dockera hosta

Bezpieczniej, ale bez Docker-from-Docker:

```bash
make terminal
```

## Obraz tylko Claude

```bash
make build-claude
IMAGE_LOCAL=orcan:claude make terminal-docker
```

## Rebuild po zmianach Dockerfile lub rootfs

```bash
make rebuild          # pełny
# albo
make rebuild-claude
make down
make terminal-docker
```

## Sprawdzenie path parity

```bash
make path-check
```

## Wewnątrz kontenera

| Akcja | Polecenie |
| --- | --- |
| Lista workspace'ów | `orcan-workspaces` |
| Status context pack | `orcan-context-status` |
| Seed wszystkich projektów | `orcan-init-projects` |
| Utwórz session brief | `orcan-session-brief` |
| Helper statusu AI | `orcan-ai-statusline` |
| Cursor CLI | `agent` / alias `ag` |
| Claude Code | `claude` / alias `cc` |

Klawisze launchera (menu w przeglądarce): numer workspace'a, `s` = status, `i` = wskazówka init, `q` = wyjście.

## Zatrzymanie i czyszczenie

```bash
make down                 # zatrzymaj kontenery; zachowaj ~/.config/orcan
make clean                # podobnie jak down dla stosów Compose
make clean-data           # DESTRUKCYJNE: usuwa ORCAN_DATA (loginy, cache, historia shella)
```

`make clean-data` prosi o wpisanie `yes`.

## Odinstalowanie { #odinstalowanie }

Pełne usunięcie z tego hosta:

```bash
cd /absolute/path/to/orcan
make down
make clean-data                 # wpisz yes — usuwa $ORCAN_DATA (domyślnie ~/.config/orcan)
docker images 'orcan*'          # przejrzyj lokalne tagi
docker rmi orcan:latest orcan:full orcan:claude   # opcjonalnie; dodaj tagi wersji jeśli są
rm -rf /absolute/path/to/orcan  # usuń clone, gdy skończysz
```

**Nie** musisz usuwać zamontowanych repozytoriów projektów, chyba że chcesz.

## Aktualizacja Orcana

```bash
cd /absolute/path/to/orcan
git fetch
git checkout vX.Y.Z       # albo main
make env                  # gdy zmienił się schemat konfiguracji
make rebuild              # gdy zmienił się Dockerfile/rootfs
make down && make terminal-docker
```

Wydania to tagi git + notatki GitHub Release. CI nie publikuje obrazu kontenera.

## Zobacz też

- [Szybki start](../getting-started/quickstart.md)
- [Rozwiązywanie problemów](troubleshooting.md)
- [Referencja Makefile](../reference/makefile.md)
- [FAQ](../faq.md)
