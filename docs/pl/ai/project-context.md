---
description: Orientacja agenta przy rozwoju repozytorium Orcan — cele, non-goals, gdzie co zmieniać.
tags:
  - develop
---

# Kontekst AI projektu

Jedna strona **docs** dla agentów kodujących **w repozytorium Orcan**.

**SoT w repo:** root [`AGENTS.md`](https://github.com/aKyther/orcan/blob/main/AGENTS.md) / [`CLAUDE.md`](https://github.com/aKyther/orcan/blob/main/CLAUDE.md) (trzymaj identyczne) oraz `.cursor/rules/agents.mdc` (zawsze włączona). Nie wymyślaj drugiego, sprzecznego rytuału. Publiczny indeks care/non-goals: [`docs/llms.txt`](https://akyther.github.io/orcan/latest/llms.txt) (`make docs-llms`).

W workspace orcan (np. `orcan-dev`) najpierw przeczytaj context pack workspace, potem `cd` do projektu `orcan` i trzymaj się **tego** `AGENTS.md`.

## Tożsamość produktu

- Oficjalna nazwa: **Orcan**. Identyfikatory: `orcan`, `ORCAN_*`.
- **Cursor** = edytor / CLI Cursor — nie nazwa produktu.
- Orcan to **orkiestrator kontekstu**, nie menedżer modeli.

| Element | Znaczenie |
| --- | --- |
| Workspace | Nazwany zestaw projektów = jedna dzienna praca |
| Path parity | Te same ścieżki absolutne host ↔ kontener |
| Dostęp | Domyślnie lokalne `orcan enter`; opcjonalnie `orcan up --with-ttyd` |
| Cockpit | Top bar + workspaces + osadzony tmux; zob. [Terminal UI](../guides/terminal-ui.md) |

## Cele

## Non-goals

- UI wyboru modeli / abstrakcja providera / auto-routing między CLI
- Publikacja obrazów z CI; Orcan jako produkt rejestru
- YAML user config / host-deps
- Auto-modyfikacja zamontowanych repozytoriów przy starcie kontenera
- Mylenie `make dev-*` z publicznym CLI `orcan`
- Skrót F3/Git w cockpicie — w terminalu alias **`lg`** (lazygit)
- „Naprawianie” **Alt+strzałek** przez przywrócenie Ctrl=split w cockpicie — wiele terminali dostarcza Alt jako Ctrl; nav mix jest zamierzony (`pty_tmux_nav.py` / `BROWSER_KEY_LIMIT`); zob. [Terminal UI — nav mix](../guides/terminal-ui.md#cockpit-nav-mix)

## Rytuał (host)

```bash
orcan init          # albo edycja orcan.config.json
orcan sync          # ZAWSZE po zmianie config (up nie robi sync)
orcan build         # gdy zmieniają się wejścia obrazu
orcan up            # daily; --with-ttyd dla przeglądarki
```

Preferuj live reconcile przez `orcan sync`, gdy to możliwe; recreate gdy wymagają tego overlaye (`orcan down && orcan up`). Szczegóły: [Runtime reconcile](../ideas/runtime-reconcile.md).

## Gdzie co zmieniać

| Zmiana | Miejsce |
| --- | --- |
| UX hosta / cele | `Makefile`, `scripts/repository/` |
| Izolowany preview UX / tmux | `make dev-*` / `scripts/dev/` — [Testy](../development/testing.md) |
| Reconcile host / audit workspace | `scripts/repository/reconcile-host.py`, `workspace-audit.py`; `docker/rootfs/usr/local/lib/orcan/reconcile.py` |
| Runtime kontenera | `docker/rootfs/usr/local/bin/` |
| Pakiety obrazu | `Dockerfile` |
| Terminal UI | [Terminal UI](../guides/terminal-ui.md); reguła `.cursor/rules/terminal-ui.mdc` |
| Globalne domyślne agentów w obrazie | `docker/rootfs/opt/cursor-defaults/` |
| Reguły rozwoju Orcana | `.cursor/rules/`, `AGENTS.md` / `CLAUDE.md` |
| Publiczny indeks agentów | `scripts/repository/generate-llms-txt.py` → `docs/llms.txt` |
| Docs użytkownika | `docs/` + krótki `README.md` |

## Mapa dokumentacji

| Temat | Doc |
| --- | --- |
| Mapa zmian (gdzie → plik → doc) | [change-map.md](../change-map.md) |
| Dlaczego Orcan | [why-orcan.md](../why-orcan.md) |
| Idee podstawowe | [ideas/core-ideas.md](../ideas/core-ideas.md) |
| Model mentalny | [ideas/mental-model.md](../ideas/mental-model.md) |
| Architektura | [architecture.md](../architecture.md) |
| Terminal UI | [guides/terminal-ui.md](../guides/terminal-ui.md) |
| Schemat konfiguracji | [reference/configuration.md](../reference/configuration.md) |
| Make / `dev-*` | [reference/makefile.md](../reference/makefile.md) |
| Bezpieczeństwo | [reference/security.md](../reference/security.md) |
| Wydanie | [development/release.md](../development/release.md) |
| Testy | [development/testing.md](../development/testing.md) |
| Publiczny indeks agentów | [`docs/llms.txt`](https://akyther.github.io/orcan/latest/llms.txt) |

## Definicja „gotowe”

Bez odpowiadających docs (EN + PL) zmiana zachowania/interfejsu jest niekompletna. Do UX cockpit/ttyd preferuj `make dev-restart`; przy zmianach layoutu/chrome użyj `make dev-smoke` / `dev-a11y` / `dev-visual` (zob. `make dev-checklist`). Przed „gotowe”: `make validate`, `make test-host`, oraz `make docs-check` gdy zmienił się docs/public surface.
