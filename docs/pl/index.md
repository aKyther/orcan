---
description: Orkiestrator kontekstu dla Cursor CLI i Claude Code w Dockerze — workspaces, path parity, terminal w przeglądarce.
---

# Orcan

**Orcan** to orkiestrator kontekstu dla agentów kodujących. Uruchamia **Cursor CLI** (`agent`) i **Claude Code** (`claude`) w Dockerze, z montowaniem path-parity, workspace'ami oraz terminalem w przeglądarce (ttyd → tmux → zsh).

Orcan **nie** wybiera modeli. Każde CLI używa własnego konta i ustawień modelu.

## Po co tego używać

- Trzymać ciężkie toolchainy poza hostem
- Jedna konfiguracja dla kilku repozytoriów (workspaces)
- Te same ścieżki bezwzględne na hoście i w kontenerze ([path parity](concepts/path-parity.md))
- Współdzielony kontekst agentów (ignores, `AGENTS.md` / `CLAUDE.md`) bez przepisywania każdego checkoutu przy każdym starcie

## Minimalny przykład

```bash
git clone https://github.com/aKyther/orcan.git
cd orcan
make setup PROJECT_DIR=/absolute/path/to/your/repo
make build
make terminal-docker
```

Otwórz `http://localhost:7681`, wybierz workspace, potem uruchom `agent` lub `claude`.

## Kolejne kroki

| Cel | Strona |
| --- | --- |
| Instalacja i pierwszy start | [Szybki start](getting-started/quickstart.md) |
| Wymagania | [Instalacja](getting-started/installation.md) |
| Edycja workspace'ów | [Konfiguracja](getting-started/configuration.md) |
| Codzienne workflowy | [Typowe workflowy](guides/workflows.md) |
| Gdy coś nie działa | [Rozwiązywanie problemów](guides/troubleshooting.md) |
| Cele Make | [Referencja Makefile](reference/makefile.md) |
| Jak Orcan myśli o kontekście | [Architektura](concepts/architecture.md) |
| Rozwój tego repozytorium | [Rozwój](development/overview.md) |
| Agenci AI / Cursor pracujący nad Orcanem | [Kontekst AI projektu](ai/project-context.md) |

## Status

Wersja **0.1.0** (zobacz [Changelog](changelog.md)). Dystrybucja: **git clone + Makefile**. Obrazy budujesz lokalnie (`make build`). CI nie publikuje obrazów kontenerów.

## Zobacz też

- [FAQ](faq.md)
- [Wdrożenie](deployment.md)
- [Interfejs hosta i kontenera](interface.md)
- [Repozytorium na GitHubie](https://github.com/aKyther/orcan)
