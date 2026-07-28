---
description: Krótkie odpowiedzi o Orcanie — modele, obrazy, aktualizacja, odinstalowanie, błędy i contributing.
---

# FAQ

Krótkie odpowiedzi na częste pytania o Orcana.

## Czym jest Orcan?

Orcan to **orkiestrator kontekstu pracy**. Uruchamia Cursor CLI (`agent`) i Claude Code (`claude`) w Dockerze z workspace'ami (nazwanymi zbiorami projektów), montowaniem path-parity oraz terminalem w przeglądarce.

Zanim przejdziesz dalej w FAQ, przeczytaj [Dlaczego Orcan?](why-orcan.md) oraz [Idee podstawowe](ideas/core-ideas.md).

## Czy Orcan wybiera modele AI?

**Nie.** Modele pozostają przy każdym CLI / koncie. Orcan nie przypina ani nie routuje modeli.

## Jak przełączyć projekty?

Edytuj `orcan.config.json` (lub `orcan context wizard`), potem:

```bash
orcan sync
orcan down && orcan up
```

**Nie** przekazuj `PROJECT_DIR=…` do `orcan up`.

## Dlaczego `orcan up` ignoruje zmiany w konfiguracji?

`orcan up` nie uruchamia `orcan sync`. Najpierw zawsze zastosuj konfigurację.

## Czy mogę commitować i pushować z kontenera?

**Autor commitów:** tak po `orcan sync` — hostowe `user.name` / `user.email` trafiają do `GIT_AUTHOR_*` w kontenerze.

**Push/pull po SSH:** startuj z `orcan up --with-git` (montuje `~/.ssh` oraz agenta SSH, gdy jest dostępny). Razem z DinD: `orcan up --with-docker --with-git`. Zwykłe `orcan up` nie podpina kluczy. Zobacz [Szybki start](getting-started/quickstart.md#git-w-kontenerze) i [Bezpieczeństwo](reference/security.md).

**Worktree:** opcjonalne. Domyślnie montujesz zwykłą ścieżkę klona; zaawansowana pomoc w wizardzie albo `orcan context worktree`, gdy chcesz osobny checkout pod `$ORCAN_DATA/worktrees`. Zobacz [Workspace'y](concepts/workspaces.md#git-worktree).

## Którzy agenci są zainstalowani?

Domyślnie obraz ma **obu** agentów (`orcan:latest` / `orcan:<VERSION>`). Żeby pominąć agenta, którego nie użyjesz, zbuduj **osobny lokalny tag** (bez pull; nie nadpisuje `latest`):

=== "Oba (domyślnie)"

    ```bash
    orcan build
    orcan up
    ```

=== "Tylko Claude Code"

    ```bash
    orcan build --claude
    IMAGE_LOCAL=orcan:0.1.1-claude orcan up   # VERSION z outputu builda
    ```

    Tag: `orcan:<VERSION>-claude`. Cursor CLI nie jest zainstalowany.

=== "Tylko Cursor CLI"

    ```bash
    orcan build --cursor
    IMAGE_LOCAL=orcan:0.1.1-cursor orcan up
    ```

    Tag: `orcan:<VERSION>-cursor`. Claude Code nie jest zainstalowany.

## Czy jest opublikowany obraz Docker?

**Nie** (nie z CI). W rejestrze obraz z **oboma agentami** jako `orcan:<VERSION>` / `:latest`. Tagi `-<claude|cursor>` tylko lokalnie. `orcan publish` pcha tylko obraz z oboma agentami.


## Gdzie są dane logowania / cache?

Pod `$ORCAN_DATA` (domyślnie `~/.config/orcan`):

| Ścieżka na hoście | Co |
| --- | --- |
| `claude/` | Konfiguracja Claude Code + OAuth (`.credentials.json`, settings). `CLAUDE_CONFIG_DIR` wskazuje tu, żeby login przeżywał restarty |
| `cursor/` | Home CLI Cursor |
| `cache/` | Cache narzędzi (ruff, pip, uv, …) |

Po `orcan build --force` / restarcie **nie** powinieneś musieć ponownie robić `/login`, chyba że wyczyściłeś `$ORCAN_DATA` albo nigdy nie dokończyłeś logowania przy zamontowanym volume.

## Czy mogę wyłączyć tmux?

Nie jako obsługiwany przełącznik. Launcher startuje tmux. Zamiast tego używaj wielu okien/paneli tmux.

## Jak zaktualizować?

```bash
orcan update                         # najnowszy tag release vX.Y.Z
orcan sync                           # gdy zmienił się schemat konfiguracji
orcan build --force                  # gdy zmienił się Dockerfile/rootfs
orcan down && orcan up
```

## Jak odinstalować? { #uninstall }

```bash
cd /absolute/path/to/orcan
orcan down
orcan uninstall --purge-data          # destrukcyjne: usuwa ~/.config/orcan (wpisz yes)
docker images 'orcan*'   # opcjonalnie: docker rmi …
# potem usuń katalog clone'a, jeśli go nie potrzebujesz
```

Szczegóły: [Workflowy — odinstalowanie](guides/workflows.md#uninstall).

## Jak zgłosić błąd?

Otwórz Issue na GitHubie: system, wersja Dockera, komenda `orcan`, którą uruchomiłeś, oraz logi (`orcan logs`, `orcan doctor`, `orcan context show`):

https://github.com/aKyther/orcan/issues

## Jak dołożyć własny kod / contribute?

1. Przeczytaj [Contributing](https://github.com/aKyther/orcan/blob/main/CONTRIBUTING.md).
2. Zobacz [Przegląd rozwoju](development/overview.md).
3. Otwórz PR do `main`.

## Zobacz też

- [Szybki start](getting-started/quickstart.md)
- [Rozwiązywanie problemów](guides/troubleshooting.md)
- [Konfiguracja](getting-started/configuration.md)
- [Issues na GitHubie](https://github.com/aKyther/orcan/issues)
