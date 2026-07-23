---
description: Makefile na hoście, CLI w kontenerze i orcan.config.json — Orcan nie ma REST API.
---

# Interfejs hosta i kontenera

Orcan **nie ma** HTTP / REST API.

Obsługiwane interfejsy publiczne:

1. **Makefile na hoście** — konfiguracja, build, uruchomienie, testy, docs, release
2. **CLI w kontenerze** — `agent`, `claude` oraz helpery `orcan-*`
3. **Plik konfiguracji** — `orcan.config.json` (walidowany przez skrypty hosta; zobacz JSON Schema poniżej)

## Host (Make)

Kanoniczna lista: [Referencja Makefile](reference/makefile.md).

Najważniejsze targety:

```bash
make setup | config-wizard | env
make build | build-claude
make terminal | terminal-docker
make validate | docs-check | test
make release
```

## Helpery w kontenerze

| Polecenie | Rola |
| --- | --- |
| `agent` / `ag` | Cursor CLI (pełny obraz) |
| `claude` / `cc` | Claude Code |
| `orcan-workspaces` | Lista workspace'ów |
| `orcan-context-status` | Status context pack |
| `orcan-init-projects` | Seed szablonów projektów |
| `orcan-session-brief` | Opcjonalny plik handoff sesji |
| `orcan-ai-statusline` | Opcjonalne użycie AI w statusie tmux |

## Powierzchnia konfiguracji

Zobacz [Referencję konfiguracji](reference/configuration.md) oraz [Zmienne środowiskowe](reference/environment.md).

Schema maszynowa: [`orcan.config.schema.json`](https://github.com/aKyther/orcan/blob/main/orcan.config.schema.json) (obok `orcan.config.example.json`).

## Zobacz też

- [Architektura](concepts/architecture.md)
- [Przewodnik — workflowy](guides/workflows.md)
- [Kod na GitHubie](https://github.com/aKyther/orcan)
