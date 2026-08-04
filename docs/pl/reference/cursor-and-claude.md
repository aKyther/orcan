# Domyślne Cursor i Claude

## Dwie warstwy

| Warstwa | Ścieżka | Rola |
| --- | --- | --- |
| Domyślne obrazu | `/opt/cursor-defaults` (z `docker/rootfs/opt/cursor-defaults/`) | Seedowane do `~/.cursor` przy starcie (**tylko gdy brakuje**) |
| Zamontowane projekty | Twoje repozytoria git | Opcjonalne `orcan seed` — **nie wymagane**; pack workspace wystarcza |

Orcan **nie** nadpisuje istniejących plików w `~/.cursor` przy każdym starcie.

## Uprawnienia CLI

Aktywny plik uprawnień Cursor CLI: `cli-config.json` (seedowany z domyślnych).

Reguły deny Claude Code używają tylko `Read(path)` i `Edit(path)`. Formy `Write(...)` są przestarzałe (Claude ostrzega i je ignoruje; `Edit` obejmuje wszystkie narzędzia edycji plików). Szablony Orcan i `init-ai-statusline` trzymają `Edit(**/.env)` (i pokrewne) bez `Write(...)`.

## Workspace vs projekt

- Context pack **workspace'a**: zapisywany pod `/home/developer/workspaces/<name>/` przez `init-workspace` (automatycznie przy starcie)
- Pliki **projektu** w checkoutach git: tylko jeśli uruchomisz `orcan seed` (opcjonalnie)

Zobacz [Architektura](../architecture.md).

## Status line

Opcjonalne użycie AI w statusie tmux: `init-ai-statusline` + `orcan-ai-statusline` (hooki dla Claude/Cursor). Celowo cienkie.

## Context Assertions: Claude tworzy, Cursor czyta

`orcan context hook enable` (wsadowa Reflection, szkicująca kandydatów na Context Assertions) jest Claude-only — patrz ["Wsadowa, zautomatyzowana Reflection"](../ideas/context-assertions.md#wsadowa-zautomatyzowana-reflection), dlaczego własny hook `stop` Cursora nie jest tu podpięty. Cursor i tak dostaje ten sam skompilowany `CONTEXT-ASSERTIONS.md`, bo `init-workspace` pisze `AGENTS.md` (Cursor) i `CLAUDE.md` (Claude) z identyczną treścią — bez osobnej ścieżki do utrzymania dla Cursora.

## To repozytorium

Gdy rozwijasz **samego Orcana**, przeczytaj też root `AGENTS.md` oraz `.cursor/rules/` — dotyczą repo Orcana, nie każdego zamontowanego projektu klienta.

## Zobacz też

- [Architektura](../architecture.md)
- [Kontekst AI projektu](../ai/project-context.md)
- [Workspaces](../concepts/workspaces.md)
- [Bezpieczeństwo](security.md)
