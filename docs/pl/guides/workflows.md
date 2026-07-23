---
description: Typowe workflowy Orcana — najpierw scenariusze dnia, potem komendy Make.
---

# Typowe workflowy

Te scenariusze zakładają, że znasz już [Idee podstawowe](../ideas/core-ideas.md). Polecenia na **hoście**, o ile nie oznaczono **(kontener)**.

## Scenariusz: start dnia w jednym kontekście

Masz już skonfigurowane workspace'y. Chcesz terminal w przeglądarce i wczorajsze mounty.

**Idea:** odtwórz sesję bez regenerowania konfiguracji.

```bash
cd /absolute/path/to/orcan
make terminal-docker
```

Otwórz `http://localhost:7681` i wybierz workspace.

!!! note
    `make terminal*` **nie** uruchamia `make env`. Jeśli zmieniłeś `orcan.config.json`, najpierw zastosuj konfigurację.

## Scenariusz: przełączenie klienta lub linii produktu

**Problem:** inny zestaw repo to dzisiejszy kontekst.  
**Podejście:** edytuj listę workspace'ów (lub włącz inny), zastosuj konfigurację, odtwórz kontener.

```bash
make config-wizard    # albo edytuj orcan.config.json
make env
make init-project-all # opcjonalne seedy w każdej ścieżce projektu
make down
make terminal-docker
```

## Scenariusz: bezpieczniejszy terminal bez socketa Dockera hosta

**Kompromis:** brak Docker-from-Docker; mniejszy blast radius.

```bash
make terminal
```

## Scenariusz: tylko Claude

**Idea:** mniejszy obraz, gdy Cursor CLI nie jest potrzebny.

```bash
make build-claude
IMAGE_LOCAL=orcan:claude make terminal-docker
```

## Scenariusz: rebuild po zmianach Dockerfile lub rootfs

**Idea:** opis kontekstu ten sam; zmienił się **obraz narzędzi**.

```bash
make rebuild          # pełny
# albo
make rebuild-claude
make down
make terminal-docker
```

## Scenariusz: weryfikacja path parity

**Dlaczego:** zagnieżdżony Docker działa tylko przy zgodnych ścieżkach bezwzględnych.

```bash
make path-check
```

## Wewnątrz kontenera

| Potrzeba | Polecenie |
| --- | --- |
| Lista workspace'ów | `orcan-workspaces` |
| Status context pack | `orcan-context-status` |
| Seed wszystkich projektów | `orcan-init-projects` |
| Session brief | `orcan-session-brief` |
| Helper statusu AI | `orcan-ai-statusline` |
| Cursor CLI | `agent` / `ag` |
| Claude Code | `claude` / `cc` |

Klawisze launchera: numer workspace'a, `s` = status, `i` = wskazówka init, `q` = wyjście.

## Stop, czyszczenie, odinstalowanie

```bash
make down                 # zatrzymaj; zachowaj ~/.config/orcan
make clean                # styl compose down
make clean-data           # DESTRUKCYJNE: usuwa ORCAN_DATA (wpisz yes)
```

Pełne usunięcie: [Odinstalowanie](#odinstalowanie).

## Odinstalowanie { #odinstalowanie }

```bash
cd /absolute/path/to/orcan
make down
make clean-data
docker images 'orcan*'
docker rmi orcan:latest orcan:full orcan:claude   # opcjonalnie
rm -rf /absolute/path/to/orcan                    # opcjonalnie
```

Zamontowane repo projektów zostają, dopóki sam ich nie usuniesz.

## Aktualizacja Orcana

```bash
cd /absolute/path/to/orcan
git fetch
git checkout vX.Y.Z       # albo main
make env                  # gdy zmienił się schemat konfiguracji
make rebuild              # gdy zmienił się Dockerfile/rootfs
make down && make terminal-docker
```

## Zobacz też

- [Szybki start](../getting-started/quickstart.md)  
- [Rozwiązywanie problemów](troubleshooting.md)  
- [Referencja Makefile](../reference/makefile.md)  
- [FAQ](../faq.md)
