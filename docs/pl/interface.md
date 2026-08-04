---
description: CLI orcan na hoście, CLI w kontenerze i orcan.config.json — Orcan nie ma REST API.
---

# Interfejs hosta i kontenera

To powierzchnia **kontraktu** po poznaniu modelu mentalnego: `orcan` na hoście, CLI w kontenerze, konfiguracja JSON. Orcan **nie ma** HTTP / REST API.

Obsługiwane interfejsy publiczne:

1. **CLI `orcan`** — konfiguracja, build, uruchomienie, diagnostyka (zobacz [Referencja CLI](reference/cli.md))
2. **CLI w kontenerze** — `agent`, `claude` oraz helpery `orcan-*`
3. **Plik konfiguracji** — `orcan.config.json` (walidowany przez skrypty hosta; zobacz JSON Schema poniżej)

## Host (`orcan`)

Najważniejsze komendy:

```bash
orcan init | sync | context show
orcan build [--claude|--cursor] [--force]
orcan up | up --with-docker | up --with-git | down
orcan logs | doctor | url
```

Rytuał użytkownika: `orcan init` → `orcan build` → `orcan up`. Po edycji konfiguracji: `orcan sync && orcan down && orcan up`.

## Make dla maintainerów

Checkout gita ma też **Makefile** pod docs, testy i release — nie do codziennej pracy. Zobacz [Referencja Makefile](reference/makefile.md) oraz [Przegląd rozwoju](development/overview.md).

## Helpery w kontenerze

| Polecenie | Rola |
| --- | --- |
| `agent` / `ag` | Cursor CLI (pełny obraz) |
| `claude` / `cc` | Claude Code |
| `orcan-workspaces` | Lista workspace'ów |
| `orcan-context-status` | Status context pack |
| `orcan-init-projects` | Opcjonalnie: seed szablonów projektów (zaawansowane) |
| `orcan-session-brief` | Opcjonalny plik handoff sesji |
| `orcan-ai-statusline` | Opcjonalne użycie AI w statusie tmux |

## Powierzchnia konfiguracji

Zobacz [Referencję konfiguracji](reference/configuration.md) oraz [Zmienne środowiskowe](reference/environment.md).

Schema maszynowa: [`orcan.config.schema.json`](https://github.com/aKyther/orcan/blob/main/orcan.config.schema.json) (obok `orcan.config.example.json`).

## Zobacz też

- [Architektura](architecture.md)
- [Przewodnik — workflowy](guides/workflows.md)
- [Kod na GitHubie](https://github.com/aKyther/orcan)
