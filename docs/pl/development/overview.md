# Przegląd rozwoju

Przewodnik dla osób i agentów kodujących, którzy zmieniają repozytorium **Orcan**.

## Lokalne przygotowanie

```bash
git clone https://github.com/aKyther/orcan.git
cd orcan
orcan init "$(pwd)"
make validate
make test-host
```

Build i smoke (wymaga Dockera; domyślnie używa Codexa):

```bash
orcan build --agent codex
make test
```

Dokumentacja:

```bash
make docs-check
make docs-serve
```

Manualne testy UX działają w osobnym kontenerze developerskim:

```bash
make dev-start
# zmień UX, następnie:
make dev-restart
make dev-doctor
make dev-smoke
make dev-stop
```

## Mapa repozytorium

| Ścieżka | Rola |
| --- | --- |
| `Dockerfile` | Build obrazu |
| `docker-compose*.yml` | Nakładki runtime |
| `docker/rootfs/` | Pliki kopiowane do obrazu |
| `cockpit/` | Cockpit TUI (agent-launcher) |
| `scripts/repository/` | Helpery hosta (config, release, validate) |
| `scripts/dev/` | Preview z checkoutu; odkrywaj przez `make dev-*` |
| `Makefile` | Cienki UI hosta |
| `orcan.config.example.json` | Szablon konfiguracji |
| `docs/` | Strona MkDocs |
| `tests/` | Testy hosta + smoke + path-parity + `dev-test` |
| `AGENTS.md` / `CLAUDE.md` | Orientacja AI dla **tego** repo (trzymaj identyczne) |
| `.cursor/rules/` | Reguły Cursor dla **tego** repo |

## Reguły separacji

- Reguły repo (`.cursor/`) ≠ domyślne obrazu (`docker/rootfs/opt/cursor-defaults/`)
- Skrypty kontenera leżą pod `docker/rootfs/usr/local/bin/`
- Helpery produktu na hoście leżą pod `scripts/repository/`
- Preview UX / tmux tylko z checkoutu leżą pod `scripts/dev/` (nigdy nie instaluj ich jako `orcan` w `PATH`)
- Konfiguracja użytkownika to wyłącznie JSON (`orcan.config.json`) — bez stosu PyYAML na hoście

## Styl kodowania

- Małe, skupione diffy
- Preferuj istniejące cele Makefile
- Prosty język B1–B2 w dokumentacji użytkownika
- Trzymaj się [docs/STYLE_GUIDE.md](https://github.com/aKyther/orcan/blob/main/docs/STYLE_GUIDE.md)
- Nie dokumentuj poleceń, których nie ma
- Nie wymyślaj funkcji w docs

## Definicja „gotowe”

Przy zmianie zachowania zaktualizuj w razie potrzeby:

1. Kod / skrypty / Compose / Dockerfile
2. Testy (`make validate`, oraz `make test` przy zmianach zachowania Dockera)
3. Docs pod `docs/` (oraz krótkie wskazówki w README)
4. `AGENTS.md` / `.cursor/rules`, jeśli zmienia się rytuał lub granice agentów
5. `CHANGELOG.md` przy zmianach widocznych dla użytkownika
6. `cockpit/pyproject.toml` (wersja) tylko przy cięciu wydania

## Zobacz też

- [Testy](testing.md)
- [Proces wydania](release.md)
- [Kontekst AI projektu](../ai/project-context.md)
- [Architektura](../architecture.md)
