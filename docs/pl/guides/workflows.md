---
description: Typowe workflowy Orcana — najpierw scenariusze dnia, potem komendy CLI `orcan`.
---

# Typowe workflowy

Te scenariusze zakładają, że znasz już [Idee podstawowe](../ideas/core-ideas.md). Polecenia na **hoście**, o ile nie oznaczono **(kontener)**.

## Scenariusz: start dnia w jednym kontekście

Masz już skonfigurowane workspace'y. Chcesz terminal w przeglądarce i wczorajsze mounty.

**Idea:** odtwórz sesję bez regenerowania konfiguracji.

```bash
cd /absolute/path/to/orcan
orcan up
```

Otwórz `http://localhost:7681` i wybierz workspace.

!!! note
    `orcan up` **nie** uruchamia `orcan sync`. Jeśli zmieniłeś `orcan.config.json`, najpierw zastosuj konfigurację.

## Scenariusz: przełączenie klienta lub linii produktu

**Problem:** inny zestaw repo to dzisiejszy kontekst.  
**Podejście:** edytuj listę workspace'ów (lub włącz inny), zastosuj konfigurację, odtwórz kontener.

```bash
orcan context wizard    # albo edytuj orcan.config.json
orcan sync
orcan down
orcan up
```

## Scenariusz: bezpieczniejszy terminal bez socketa Dockera hosta

**Kompromis:** brak Docker-from-Docker; mniejszy blast radius. To jest **domyślne**.

```bash
orcan up
```

## Scenariusz: terminal z socketem Dockera hosta (DinD)

**Kiedy:** zagnieżdżony Compose / Docker z wnętrza kontenera.

```bash
orcan up --with-docker
```

## Scenariusz: zainstaluj tylko jednego agenta

**Idea:** nie instaluj agenta, którego nie użyjesz (mniejszy obraz, te same tagi).

```bash
orcan build --claude   # → orcan:<VERSION>-claude
IMAGE_LOCAL=orcan:0.1.1-claude orcan up
# albo
orcan build --cursor   # → orcan:<VERSION>-cursor
IMAGE_LOCAL=orcan:0.1.1-cursor orcan up
```

## Scenariusz: rebuild po zmianach Dockerfile lub rootfs

**Idea:** opis kontekstu ten sam; zmienił się **obraz narzędzi**.

```bash
orcan build --force       # pełny obraz; pomiń pull, zbuduj lokalnie
# albo
orcan build --claude --force
orcan down
orcan up
```

## Scenariusz: weryfikacja path parity

**Dlaczego:** zagnieżdżony Docker działa tylko przy zgodnych ścieżkach bezwzględnych.

```bash
orcan context show
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
orcan down                 # zatrzymaj; zachowaj ~/.config/orcan
orcan uninstall --purge-data           # DESTRUKCYJNE: usuwa ORCAN_DATA (wpisz yes)
```

Pełne usunięcie: [Odinstalowanie](#odinstalowanie).

## Odinstalowanie { #odinstalowanie }

```bash
cd /absolute/path/to/orcan
orcan down
orcan uninstall --purge-data
docker images 'orcan*'
docker rmi orcan:latest 'orcan:*'   # opcjonalnie: usuń lokalne tagi
rm -rf /absolute/path/to/orcan                    # opcjonalnie
```

Zamontowane repo projektów zostają, dopóki sam ich nie usuniesz.

## Aktualizacja Orcana

```bash
cd /absolute/path/to/orcan
orcan update                # albo: git fetch && git checkout vX.Y.Z
orcan sync                  # gdy zmienił się schemat konfiguracji
orcan build --force         # gdy zmienił się Dockerfile/rootfs
orcan down && orcan up
```

## Zobacz też

- [Szybki start](../getting-started/quickstart.md)  
- [Rozwiązywanie problemów](troubleshooting.md)  
- [Referencja CLI](../reference/cli.md)  
- [FAQ](../faq.md)
