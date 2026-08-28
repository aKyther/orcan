---
description: Publiczne CLI orcan — komendy, flagi oraz granica maintainer vs użytkownik końcowy.
tags:
  - reference
---

# Referencja CLI

Publiczny interfejs Orcan to komenda **`orcan`** (Bash). Cele Make zostają tylko dla **maintainerów** (docs, testy, release).

## Instalacja

```bash
curl -fsSL https://raw.githubusercontent.com/aKyther/orcan/main/install.sh | bash
```

| Ścieżka | Rola |
| --- | --- |
| `~/.local/share/orcan` | Klon gita (`ORCAN_ROOT`) |
| `~/.local/bin/orcan` | Launcher |
| `~/.config/orcan` | Config + `.env` + `mounts/*` (`ORCAN_HOME`) *oraz* dane narzędzi / loginy (`ORCAN_DATA`) — ten sam katalog domyślnie |

Nadpisz tylko gdy trzeba: `ORCAN_HOME=/path` albo `ORCAN_USE_CWD=1` (użyj `./orcan.config.json` w bieżącym katalogu).

## Zależności hosta

Komenda `orcan` to **Bash**, ale konfiguracja na hoście idzie przez **Python 3** (sama stdlib — bez pip/venv):

| Potrzeba | Używane przez |
| --- | --- |
| Bash, Git | CLI, instalacja, `orcan update`/`upgrade`/`downgrade` |
| **Python 3** | `orcan sync`, `init`, `context` (show / add / hook) |
| Docker Compose v2 | `orcan build`, `up`, `down`, … |

Sprawdź: `orcan doctor`. Szczegóły: [Instalacja](../getting-started/installation.md).

## Komendy

| Komenda | Rola |
| --- | --- |
| `orcan init` | Bez PATH: TUI do tworzenia/edycji workspace'ów (domyślnie) + sync + show. `--cli`: stary, sekwencyjny kreator promptów zamiast TUI |
| `orcan init PATH` | Bez interakcji: scaffold jednego projektu (skrypty/CI) + sync + show |
| `orcan sync [--prune-orphans]` | Zastosuj `orcan.config.json` → `.env` + `mounts/*`; live-reconcile działającego kontenera. `--prune-orphans` dodatkowo zabija osierocone sesje tmux po usuniętym/zmienionym workspace (domyślnie: tylko raport) |
| `orcan sync --context [--watch\|--once] [--force] [--interval N]` | Tylko host: kompilacja/import dropów Context Assertions bez pełnego sync configu (`scripts/repository/context_syncd.py`). `--once` pomija, gdy fingerprint inboxu się nie zmienił; `--watch` polluje (domyślnie 15s). Respektuje pauzę cockpit **`[p]`** / wyłączenie **`[o]`** przez `$ORCAN_DATA/history/supervisor/automation.json`. Patrz [Context Assertions](../ideas/context-assertions.md) |
| `orcan migrate [--yes] [--no-symlink]` | Przenieś skonfigurowane projekty pod managed root (`ORCAN_PROJECTS_ROOT`); dry-run bez `--yes` — mniej przyszłych recreate kontenera |
| `orcan settings` | Edycja ustawień narzędziowych (okna/prefix tmux, port/font ttyd) — osobno od workspace'ów/projektów |
| `orcan context show` | Lista workspace'ów + path parity |
| `orcan context add PATH` | Dodaj projekt (`--workspace`, `--force`) |
| `orcan context tui` | TUI: skan katalogu-rodzica, multi-select repo, create/update workspace; opcjonalnie jeden branch → managed worktree na każde repo (`--sync`, `--yes`). Przy istniejącym configu odpala się w **trybie zarządzania** — zmiana nazwy/ścieżki/usuwanie istniejących workspace'ów i projektów (`n` przełącza na ekran skanowania, żeby dodać kolejne); to właśnie uruchamia domyślnie `orcan init` |
| `orcan context add --from-worktree REPO SELECTOR` | Dodaj istniejący git worktree (selektor: branch, indeks lub ścieżka) |
| `orcan context worktrees [REPO]` | Lista git worktree (`git worktree list`) |
| `orcan context worktree create …` | Utwórz worktree (managed pod `$ORCAN_PROJECTS_ROOT/.worktrees` przy `--workspace`) i podepnij. Jeśli `--branch NAME` nie istnieje lokalnie, najpierw próbowany jest bezpieczny `git fetch origin NAME` (nigdy nie pyta o poświadczenia, timeout 5s) — znaleziony na remote → worktree z niego; nie znaleziony/niedostępny → nowy branch z `--start-point` (domyślnie `HEAD`), tak jak wcześniej |
| `orcan context worktree remove --path PATH` | Usuń jeden managed worktree |
| `orcan context worktree remove --workspace NAME` | Usuń wszystkie managed worktree workspace'a (i wypnij z configu) |
| `orcan context worktree prune [--force] [--no-config]` | Pogódź `$ORCAN_PROJECTS_ROOT/.worktrees/registry.json` ze stanem na dysku (i `orcan.config.json`); domyślnie dry-run, `--force` sprząta |
| `orcan context assert propose …` | Reflection: naszkicuj Context Assertion (treść + uzasadnienie + applicability); status `proposed` |
| `orcan context assert accept\|reject\|retire ID` | Review Gate: `proposed` → `accepted`/`rejected`, albo `accepted` → `retired` — nigdy automatycznie |
| `orcan context assert list\|show\|select\|root` | Przegląd store'u; `select` pokazuje podgląd tego, co skompilowałby `orcan sync` |
| `orcan context hook enable\|disable\|status [WORKSPACE ...] [--all]` | Włącz/wyłącz hook `Stop` Claude (wsadowa Reflection) w `.claude/settings.json` wygenerowanego katalogu głównego workspace'u — **domyślnie włączony**, dosiewany przy pierwszej `orcan sync` dla workspace'u; `disable` zostaje przy kolejnych sync'ach. Bez `WORKSPACE`/`--all` odgaduje workspace na podstawie `cwd`, jeśli ten leży wewnątrz zarejestrowanego projektu |
| *(wewnątrz kontenera)* `orcan-context-propose` / `orcan-context-review` | Szkicowanie/review bez terminala hosta — zrzut do zamontowanej skrzynki, importowany przy najbliższym `orcan sync`. `orcan-context-review [--no-check]` wstępnie sprawdza kandydatów pod kątem duplikatów/sprzeczności z `CONTEXT-ASSERTIONS.md` (tylko podpowiedź, nigdy bramka). Patrz [Context Assertions](../ideas/context-assertions.md) |
| *(wewnątrz kontenera)* `orcan-context-scan` | Feeder Reflection z dysku (`--watch`, `--all-workspaces`); domyślny driver **recap** przez `orcan-context-recap`. Patrz [Context Assertions](../ideas/context-assertions.md) |
| *(wewnątrz kontenera)* `orcan-context-recap` | Kaskadowy compact sesji + flush do inbox (wołany przez scan; zwykle nie ręcznie). Patrz [Context Assertions](../ideas/context-assertions.md) |
| *(wewnątrz kontenera)* `orcan-context-model-check` | Probe Claude/Haiku pod recap; `--quick` (PATH/wersja), `--refresh` (aktualizacja cache w `automation.json`). Patrz [Context Assertions](../ideas/context-assertions.md) |
| *(wewnątrz kontenera)* `orcan-inbox` | Kolejka przekazywania zadań agentów w `.orcan/tasks/` (`propose`, `approve`, `claim`, `complete`, `list`, `watch`). Patrz [Skrzynka agentów](../ideas/agent-inbox.md) |
| `orcan up [--with-ttyd \| --with-ttyd-auth USER:PASS] [--with-docker \| --with-network NAME] [--with-git]` | Start kontenera (`orcan enter` lokalnie; **jedna** ścieżka przeglądarki: `--with-ttyd` albo `--with-ttyd-auth`); opcjonalnie socket **albo** join sieci (wybierz jedno) + SSH; podpowiada nowszy release; status hooka `Stop` (Claude) |
| `orcan down` | Stop kontenerów |
| `orcan build [--claude|--cursor] [--force] [--no-cache]` | Obaj agenci → `orcan:latest` + `orcan:<VERSION>` (pull lub build). `--claude` / `--cursor` → `orcan:<VERSION>-claude\|cursor` (bez pull; nie nadpisuje `latest`). Nigdy nie publikuje |
| `orcan pull` | Pull obu agentów `orcan:<VERSION>` → `orcan:latest` |
| `orcan publish` | Push obu agentów `orcan:latest` (**ręcznie**; nie `-claude`/`-cursor`) |
| `orcan url` | URL terminala w przeglądarce (wymaga `orcan up --with-ttyd`) |
| `orcan logs [docker\|supervisor\|context-scan]` | Logi kontenera (domyślnie) albo trwałe logi supervisord / skanera Reflection |
| `orcan enter` / `orcan go-in` | Lokalny terminal do działającego kontenera (`--launcher` domyślnie, `--shell`, `--tmux [SESSION]`) |
| `orcan update` | Kanał dev: fast-forward tego checkoutu do `origin/main` |
| `orcan upgrade [--to VERSION]` | Kanał release: najnowszy tag release `vX.Y.Z` (domyślnie), albo `--to` przypina konkretny (w górę lub w dół) |
| `orcan downgrade [--to VERSION]` | Poprzedni release SemVer, albo starszy `--to` (odmawia nowszych targetów) |
| `orcan doctor` | Zdrowie hosta / configu / kontenera (supervisord, stan automatyzacji context, probe modelu recap — gdy obraz to wspiera) |
| `orcan uninstall [--purge-data]` | Usuń CLI (opcjonalnie `ORCAN_DATA`) |
| `orcan version` / `orcan help` | Wersja / pomoc |

### Opcjonalne

| Komenda | Rola |
| --- | --- |
| `orcan seed [--all] [--dry-run]` | Szablony/ignores w checkoutach git — **rzadko potrzebne**; pack workspace wystarcza |

## Rytuał

```bash
orcan init
orcan build
orcan up              # lokalnie — orcan enter na tej samej maszynie
# zdalnie w przeglądarce: orcan up --with-ttyd
```

Po edycji konfiguracji:

```bash
# edytuj ~/.config/orcan/orcan.config.json
orcan sync
orcan down && orcan up
```

`orcan up` **nie** uruchamia `sync`.

### Flagi `orcan up`

| Flaga | Efekt |
| --- | --- |
| *(brak)* | Tylko lokalnie — bez publikacji portu ttyd; użyj `orcan enter` |
| `--with-ttyd` \| `--with-ttyd-auth USER:PASS` | **Wybierz jedno.** `--with-ttyd`: terminal w przeglądarce, bez hasła. `--with-ttyd-auth USER:PASS`: ten sam terminal **z** HTTP basic auth. Nie podawaj obu. (`TTYD_BIND` domyślnie `0.0.0.0`.) |
| `--with-docker` \| `--with-network NAME` | **Wybierz jedno.** `--with-docker`: montuje `/var/run/docker.sock` (Docker-from-Docker). `--with-network NAME`: dołącza do istniejącej sieci Docker (bez socketa) |
| `--with-git` | Montuje hostowy `~/.ssh` tylko do odczytu (+ agent SSH, gdy `SSH_AUTH_SOCK` jest ustawiony) do push/pull |

Pozostałe flagi łączą się z wybraną ścieżką przeglądarki, np. `orcan up --with-ttyd --with-git` albo `orcan up --with-ttyd-auth user:pass --with-network my-net`.

Tożsamość **autora** Gita zawsze synchronizuje `orcan sync` (`GIT_AUTHOR_*` z hostowego `user.name` / `user.email`). Klucze SSH są podpinane tylko przez `--with-git`. Flagi opcjonalne wypisują ostrzeżenie bezpieczeństwa — agenci w środku mogą użyć zamontowanego socketa lub kluczy. Drabinka możliwości i kompromisy: [Bezpieczeństwo](security.md), [Workflowy](../guides/workflows.md).

## Make dla maintainerów

Z checkoutu gita: `make validate`, `make test-host`, `make docs*`, `make release*`, `make registry-*`. Zobacz [Development](../development/overview.md).
