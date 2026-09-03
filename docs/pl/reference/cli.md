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
| `orcan migrate [--yes] [--no-symlink]` | Przenieś skonfigurowane projekty pod managed root (`ORCAN_PROJECTS_ROOT`); dry-run bez `--yes` — mniej przyszłych recreate kontenera |
| `orcan settings` | Edycja ustawień narzędziowych (okna/prefix tmux, port/font ttyd) — osobno od workspace'ów/projektów |
| `orcan context show` | Lista workspace'ów + path parity |
| `orcan context add PATH` | Dodaj projekt (`--workspace`, `--force`) |
| `orcan context tui` | TUI: skan katalogu i kompaktowa lista **will add**. Każdy wybrany projekt może niezależnie działać jako mount as-is albo managed worktree na jednym branchu: **`t`** przełącza wszystkie wybrane repo Git, a w podglądzie **Tab** klawisz **`b`** przełącza tylko wskazany projekt. Gdy nic nie wybrano, **Enter** otwiera wskazany folder; po zaznaczeniu projektów zatwierdza wybór. Ekran zarządzania ma zwijane grupy workspace (**←/→**). Domyślny skan pokazuje dzieci (`D` przełącza wnuki), a `h` przywołuje ostatnie wybory. |
| `orcan context add --from-worktree REPO SELECTOR` | Dodaj istniejący git worktree (selektor: branch, indeks lub ścieżka) |
| `orcan context worktrees [REPO]` | Lista git worktree (`git worktree list`) |
| `orcan context worktree create …` | Utwórz worktree (managed pod `$ORCAN_PROJECTS_ROOT/.worktrees` przy `--workspace`) i podepnij. Jeśli `--branch NAME` nie istnieje lokalnie, najpierw próbowany jest bezpieczny `git fetch origin NAME` (nigdy nie pyta o poświadczenia, timeout 5s) — znaleziony na remote → worktree z niego; nie znaleziony/niedostępny → nowy branch z `--start-point` (domyślnie `HEAD`), tak jak wcześniej |
| `orcan context worktree remove --path PATH` | Usuń jeden managed worktree |
| `orcan context worktree remove --workspace NAME` | Usuń wszystkie managed worktree workspace'a (i wypnij z configu) |
| `orcan context worktree prune [--force] [--no-config]` | Pogódź `$ORCAN_PROJECTS_ROOT/.worktrees/registry.json` ze stanem na dysku (i `orcan.config.json`); domyślnie dry-run, `--force` sprząta |
| *(wewnątrz kontenera)* `orcan-inbox` | Kolejka przekazywania zadań agentów w `.orcan/tasks/` (`propose`, `approve`, `claim`, `complete`, `list`, `watch`). Patrz [Skrzynka agentów](../ideas/agent-inbox.md) |
| `orcan up [--with-ttyd \| --with-ttyd-auth USER:PASS] [--with-docker \| --with-network NAME] [--with-git]` | Start kontenera (`orcan enter` lokalnie; **jedna** ścieżka przeglądarki: `--with-ttyd` albo `--with-ttyd-auth`); opcjonalnie socket **albo** join sieci (wybierz jedno) + SSH; podpowiada nowszy release |
| `orcan down` | Stop kontenerów |
| `orcan build --agent NAME [...] \| --all-agents [--force] [--no-cache]` | Buduje standardowy obraz `orcan:latest` + `orcan:<VERSION>` z jawnym wyborem klientów (`cursor`, `claude`, `codex`, `gemini`, `copilot`). Wybór zapisuje `/etc/orcan/agents.json`; nigdy nie publikuje |
| `orcan status` | Wersja produktu, podsumowanie runtime i manifest agentów obrazu |
| `orcan pull` | Pull przenośnego obrazu ze wszystkimi agentami `orcan:<VERSION>` → `orcan:latest` |
| `orcan publish` | Push obrazu ze wszystkimi agentami `orcan:latest` (**ręcznie**; częściowe obrazy są odrzucane) |
| `orcan url` | URL terminala w przeglądarce (wymaga `orcan up --with-ttyd`) |
| `orcan enter` / `orcan go-in` | Lokalny terminal do działającego kontenera (`--launcher` domyślnie, `--shell`, `--tmux [SESSION]`) |
| `orcan update` | Kanał dev: fast-forward tego checkoutu do `origin/main` |
| `orcan upgrade [--to VERSION]` | Kanał release: najnowszy tag release `vX.Y.Z` (domyślnie), albo `--to` przypina konkretny (w górę lub w dół) |
| `orcan downgrade [--to VERSION]` | Poprzedni release SemVer, albo starszy `--to` (odmawia nowszych targetów) |
| `orcan uninstall [--purge-data] [--purge-images]` | Zatrzymaj/usuń runtime i CLI Orcana. Dane/obrazy są opt-in; `ORCAN_PROJECTS_ROOT` i skonfigurowane projekty zostają |
| `orcan version` / `orcan help` | Wersja / pomoc |

### Opcjonalne

| Komenda | Rola |
| --- | --- |
| `orcan seed [--all] [--dry-run]` | Szablony/ignores w checkoutach git — **rzadko potrzebne**; pack workspace wystarcza |

## Rytuał

```bash
orcan init
orcan build --agent codex
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
