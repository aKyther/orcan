---
description: Gdzie zmieniać co w Orcanie — ścieżki w repo i odpowiadające docs dla ludzi i agentów.
tags:
  - guide
  - develop
---

# Mapa zmian

Krótki indeks **gdzie edytować** — i który doc to wyjaśnia. Orientacja agenta w tym repo: też [Kontekst AI](ai/project-context.md) oraz root [`AGENTS.md`](https://github.com/aKyther/orcan/blob/main/AGENTS.md).

## Zmiana produktu → miejsce → doc

| Chcesz zmienić… | Edytuj tu | Czytaj |
| --- | --- | --- |
| UX hosta / cele Make | `Makefile`, `scripts/repository/` | [Makefile](reference/makefile.md) |
| Cockpit TUI (`agent-launcher`) | `cockpit/src/orcan_cockpit/` (`shortcuts.py`, `activity.py`, `top_bar.py`) | [Workflowy — lokalny terminal](guides/workflows.md#local-terminal), [Terminal UI](guides/terminal-ui.md) |
| Recap sesji / driver skanu | `docker/rootfs/usr/local/lib/orcan/recap.py`, `orcan-context-recap`, `orcan-context-scan` | [Context Assertions](ideas/context-assertions.md), [Environment](reference/environment.md) |
| Probe modelu recap | `docker/rootfs/usr/local/lib/orcan/context_model_check.py`, `orcan-context-model-check` | [Context Assertions](ideas/context-assertions.md), [Environment](reference/environment.md) |
| Supervisord / skan Reflection | `docker/rootfs/etc/orcan/supervisor.d/`, `orcan-supervisord`, `orcan-context-scan`, `session_scan.py` | [Docker](reference/docker.md#process-layout-supervisord), [Context Assertions](ideas/context-assertions.md) |
| Host sync context / kontrola automatyzacji | `scripts/repository/context_syncd.py`, `docker/rootfs/usr/local/lib/orcan/automation.py` | [Context Assertions](ideas/context-assertions.md), [CLI](reference/cli.md) |
| Izolowany preview UX / tmux (checkout) | `make dev-*`, `scripts/dev/` | [Testy](development/testing.md), [Makefile](reference/makefile.md) |
| Schemat config / wizard | `scripts/repository/config-*.py`, `apply-config.py` | [Referencja konfiguracji](reference/configuration.md), [Przewodnik](getting-started/configuration.md) |
| Context Assertions / compile | `scripts/repository/context_assertions.py`, `compile_context.py` | [Context Assertions](ideas/context-assertions.md) |
| Managed workspaces / worktrees | `scripts/repository/managed_workspace.py`, `git_worktrees.py` | [Workspaces](concepts/workspaces.md), [Runtime reconcile](ideas/runtime-reconcile.md) |
| Reconcile host / audit workspace | `scripts/repository/reconcile-host.py`, `workspace-audit.py`; `docker/rootfs/usr/local/lib/orcan/reconcile.py` | [Runtime reconcile](ideas/runtime-reconcile.md), [CLI](reference/cli.md) |
| Binaria runtime w kontenerze | `docker/rootfs/usr/local/bin/` | [Docker](reference/docker.md), [Interfejs](interface.md) |
| Pakiety obrazu / agenci | `Dockerfile` | [Docker](reference/docker.md), [Wdrożenie](deployment.md) |
| Wygląd terminala (ttyd / tmux / zsh / …) | `docker/rootfs/` (mapa w Terminal UI) | [Terminal UI](guides/terminal-ui.md) |
| Globalne domyślne agentów w obrazie | `docker/rootfs/opt/cursor-defaults/` | [Cursor i Claude](reference/cursor-and-claude.md) |
| Reguły przy rozwoju Orcana | `.cursor/rules/`, `AGENTS.md` / `CLAUDE.md` | [Kontekst AI](ai/project-context.md) |
| Docs użytkownika / motyw site | `docs/`, `mkdocs.yml`, `overrides/` | [STYLE_GUIDE](https://github.com/aKyther/orcan/blob/main/docs/STYLE_GUIDE.md), ta strona |
| Paleta docs / favicon | `docs/assets/stylesheets/orcan.css`, `docs/assets/images/favicon.svg` | [Terminal UI](guides/terminal-ui.md) (kolory produktu) |
| Publiczny indeks docs dla agentów | `docs/llms.txt` (generowany; mapa 30s + care / non-goals) | [llms.txt](https://akyther.github.io/orcan/latest/llms.txt) |

## Strony idei (przed Make)

| Temat | Doc |
| --- | --- |
| Dlaczego Orcan | [Dlaczego Orcan?](why-orcan.md) |
| Project / Workspace / Context | [Idee podstawowe](ideas/core-ideas.md) |
| Jak elementy się łączą | [Model mentalny](ideas/mental-model.md) |
| Path parity | [Path parity](concepts/path-parity.md) |
| Architektura | [Architektura](architecture.md) |
| Trade-offy bezpieczeństwa | [Bezpieczeństwo](reference/security.md) |

## Rytuał (host)

```bash
orcan init          # albo edytuj orcan.config.json
orcan sync
orcan build         # gdy zmieniają się wejścia obrazu
orcan up            # codziennie; NIE uruchamia orcan sync
```

Po zmianach config przy działającym kontenerze: preferuj `orcan sync` (live reconcile,
gdy projekty są pod stabilnymi mountami). Recreate tylko gdy wymagają tego overlaye/flagi:
`orcan down && orcan up`.

!!! tip
    Ta strona = „gdzie klikać?”; [Kontekst AI](ai/project-context.md) = rytuał agenta; [Referencja CLI](reference/cli.md) = flagi.

## Zobacz też

- [Tagi](tags.md) — przegląd stron po etykiecie  
- [Rozwiązywanie problemów](guides/troubleshooting.md)  
- [Testy](development/testing.md)
