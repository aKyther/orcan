# Kontekst AI projektu

Jedna strona orientacyjna dla agentów kodujących pracujących **nad repozytorium Orcan**.

Przeczytaj też root [`AGENTS.md`](https://github.com/aKyther/orcan/blob/main/AGENTS.md) oraz `.cursor/rules/agents.mdc` (zawsze włączone w Cursorze). Nie wymyślaj drugiego, sprzecznego rytuału.

## Tożsamość produktu

- Oficjalna nazwa: **Orcan** (display). Identyfikatory techniczne używają małych liter `orcan` (`orcan:latest`, `ORCAN_DATA`, `orcan.config.json`).
- **Orcan** to jedyna nazwa produktu w dokumentacji i tekstach użytkownika.
- **Cursor** oznacza edytor Cursor / Cursor CLI — nie nazwę produktu.
- Orcan to **orkiestrator kontekstu**, nie menedżer modeli.

## Cele

- Workspaces + mounty path-parity
- Context pack (ignores, AGENTS/CLAUDE, Context Assertions)
- Terminal w przeglądarce: ttyd → launcher → tmux → zsh
- Warianty obrazu: pełny (Claude+Cursor) oraz tylko Claude

## Non-goals

- UI wyboru modelu / abstrakcja providera
- Auto-routing między `agent` a `claude`
- Publikacja obrazów z CI
- Automatyczna modyfikacja zamontowanych repo git przy każdym starcie kontenera

## Rytuał (host)

```bash
orcan init          # or edit orcan.config.json
orcan sync
orcan build                  # when image inputs change
orcan up        # daily; does NOT run orcan sync
```

Po edycji konfiguracji przy działającym kontenerze: `orcan sync && orcan down && orcan up`.

## Gdzie co zmieniać

| Zmiana | Miejsce |
| --- | --- |
| UX hosta / cele | `Makefile`, `scripts/repository/` |
| Store Context Assertions / Applicability Layer | `scripts/repository/context_assertions.py`, `scripts/repository/compile_context.py` |
| Runtime kontenera | `docker/rootfs/usr/local/bin/` |
| Pakiety obrazu | `Dockerfile` |
| Globalne domyślne agentów w obrazie | `docker/rootfs/opt/cursor-defaults/` |
| Reguły rozwoju Orcana | `.cursor/rules/`, `AGENTS.md` |
| Docs użytkownika | `docs/` + krótki `README.md` |

## Mapa dokumentacji

| Temat | Doc |
| --- | --- |
| Dlaczego Orcan | [why-orcan.md](../why-orcan.md) |
| Idee podstawowe | [ideas/core-ideas.md](../ideas/core-ideas.md) |
| Model mentalny | [ideas/mental-model.md](../ideas/mental-model.md) |
| Context Assertions | [ideas/context-assertions.md](../ideas/context-assertions.md) |
| Architektura | [architecture.md](../architecture.md) |
| Schemat konfiguracji | [reference/configuration.md](../reference/configuration.md) |
| Cele Make | [reference/makefile.md](../reference/makefile.md) |
| Bezpieczeństwo | [reference/security.md](../reference/security.md) |
| Wydanie | [development/release.md](../development/release.md) |
| Testy | [development/testing.md](../development/testing.md) |

## Definicja „gotowe”

Zmiana kodu jest niekompletna bez aktualizacji odpowiadających docs, gdy zmienia się zachowanie lub interfejs. Przed uznaniem za gotowe uruchom `make validate` oraz `make docs-check`.

## Zobacz też

- [Przegląd rozwoju](../development/overview.md)
- [Architektura](../architecture.md)
- [Referencja Makefile](../reference/makefile.md)
- [Bezpieczeństwo](../reference/security.md)
