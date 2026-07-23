# Domyślne Cursor i Claude

## Dwie warstwy

| Warstwa | Ścieżka | Rola |
| --- | --- | --- |
| Domyślne obrazu | `/opt/cursor-defaults` (z `docker/rootfs/opt/cursor-defaults/`) | Seedowane do `~/.cursor` przy starcie (**tylko gdy brakuje**) |
| Zamontowane projekty | Twoje repozytoria git | Opcjonalne seedy przez `make init-project` / `init-project-all` |

Orcan **nie** nadpisuje istniejących plików w `~/.cursor` przy każdym starcie.

## Uprawnienia CLI

Aktywny plik uprawnień Cursor CLI: `cli-config.json` (seedowany z domyślnych).

## Workspace vs projekt

- Context pack **workspace'a**: zapisywany pod `/home/developer/workspaces/<name>/` przez `init-workspace`
- Pliki **projektu**: tylko gdy uruchomisz cele init-project

Zobacz [Architektura](../concepts/architecture.md).

## Status line

Opcjonalne użycie AI w statusie tmux: `init-ai-statusline` + `orcan-ai-statusline` (hooki dla Claude/Cursor). Celowo cienkie.

## To repozytorium

Gdy rozwijasz **samego Orcana**, przeczytaj też root `AGENTS.md` oraz `.cursor/rules/` — dotyczą repo Orcana, nie każdego zamontowanego projektu klienta.

## Zobacz też

- [Architektura](../concepts/architecture.md)
- [Kontekst AI projektu](../ai/project-context.md)
- [Workspaces](../concepts/workspaces.md)
- [Bezpieczeństwo](security.md)
