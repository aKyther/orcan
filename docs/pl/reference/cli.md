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
| `~/.config/orcan/home` | Config + `.env` + `.orcan/*` (`ORCAN_HOME`) — **zawsze** domyślne |
| `~/.config/orcan` | Dane narzędzi / loginy (`ORCAN_DATA`) |

Nadpisz tylko gdy trzeba: `ORCAN_HOME=/path` albo `ORCAN_USE_CWD=1` (użyj `./orcan.config.json` w bieżącym katalogu).

## Zależności hosta

Komenda `orcan` to **Bash**, ale konfiguracja na hoście idzie przez **Python 3** (sama stdlib — bez pip/venv):

| Potrzeba | Używane przez |
| --- | --- |
| Bash, Git | CLI, instalacja, `orcan update` |
| **Python 3** | `orcan sync`, `init`, `context` (show / add / hook) |
| Docker Compose v2 | `orcan build`, `up`, `down`, … |

Sprawdź: `orcan doctor`. Szczegóły: [Instalacja](../getting-started/installation.md).

## Komendy

| Komenda | Rola |
| --- | --- |
| `orcan init` | Bez PATH: interaktywny kreator config (utwórz/edytuj) + sync + show |
| `orcan init PATH` | Bez interakcji: scaffold jednego projektu (skrypty/CI) + sync + show |
| `orcan sync` | Zastosuj `orcan.config.json` → `.env` + `.orcan/*` |
| `orcan context show` | Lista workspace'ów + path parity |
| `orcan context add PATH` | Dodaj projekt (`--workspace`, `--force`) |
| `orcan context add --from-worktree REPO SELECTOR` | Dodaj istniejący git worktree (selektor: branch, indeks lub ścieżka) |
| `orcan context worktrees [REPO]` | Lista git worktree (`git worktree list`) |
| `orcan context worktree create …` | Utwórz worktree (managed pod `$ORCAN_DATA/worktrees` przy `--workspace`) i podepnij |
| `orcan context worktree remove --path PATH` | Usuń jeden managed worktree |
| `orcan context worktree remove --workspace NAME` | Usuń wszystkie managed worktree workspace'a (i wypnij z configu) |
| `orcan context assert propose …` | Reflection: naszkicuj Context Assertion (treść + uzasadnienie + applicability); status `proposed` |
| `orcan context assert accept\|reject\|retire ID` | Review Gate: `proposed` → `accepted`/`rejected`, albo `accepted` → `retired` — nigdy automatycznie |
| `orcan context assert list\|show\|select\|root` | Przegląd store'u; `select` pokazuje podgląd tego, co skompilowałby `orcan sync` |
| `orcan context hook enable\|disable\|status [WORKSPACE ...] [--all]` | Włącz/wyłącz opcjonalny hook `Stop` Claude (wsadowa Reflection) w `.claude/settings.json` wygenerowanego katalogu głównego workspace'u — tam, gdzie faktycznie startują sesje Claude Code, nigdy wewnątrz checkoutu projektu; wymaga wcześniejszego `orcan sync`, potem działa od razu. Bez `WORKSPACE`/`--all` odgaduje workspace na podstawie `cwd`, jeśli ten leży wewnątrz zarejestrowanego projektu |
| *(wewnątrz kontenera)* `orcan-context-propose` / `orcan-context-review` | Szkicowanie/review bez terminala hosta — zrzut do zamontowanej skrzynki, importowany przy najbliższym `orcan sync`. `orcan-context-review [--no-check]` wstępnie sprawdza kandydatów pod kątem duplikatów/sprzeczności z `CONTEXT-ASSERTIONS.md` (tylko podpowiedź, nigdy bramka). Patrz [Context Assertions](../ideas/context-assertions.md) |
| `orcan up [--with-docker] [--with-git]` | Start terminala (socket / host SSH tylko z flagami); podpowiada, gdy jest nowszy release; po starcie wypisuje status hooka `Stop` (Claude) dla workspace'u |
| `orcan down` | Stop kontenerów |
| `orcan build [--claude|--cursor] [--force] [--no-cache]` | Obaj agenci → `orcan:latest` + `orcan:<VERSION>` (pull lub build). `--claude` / `--cursor` → `orcan:<VERSION>-claude\|cursor` (bez pull; nie nadpisuje `latest`). Nigdy nie publikuje |
| `orcan pull` | Pull obu agentów `orcan:<VERSION>` → `orcan:latest` |
| `orcan publish` | Push obu agentów `orcan:latest` (**ręcznie**; nie `-claude`/`-cursor`) |
| `orcan url` | URL terminala |
| `orcan logs` | Logi |
| `orcan enter` / `orcan go-in` | Lokalny terminal do działającego kontenera (`--launcher` domyślnie, `--shell`, `--tmux [SESSION]`) |
| `orcan update [--release\|--main]` | Najnowszy tag release `vX.Y.Z` (domyślnie); `--main` = bleeding edge |
| `orcan doctor` | Raport zdrowia hosta / configu |
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
orcan up
```

Po edycji konfiguracji:

```bash
# edytuj ~/.config/orcan/home/orcan.config.json
orcan sync
orcan down && orcan up
```

`orcan up` **nie** uruchamia `sync`.

### Flagi `orcan up`

| Flaga | Efekt |
| --- | --- |
| *(brak)* | Tylko terminal w przeglądarce — bez socketa Dockera, bez hostowego SSH |
| `--with-docker` | Montuje `/var/run/docker.sock` (Docker-from-Docker) |
| `--with-git` | Montuje hostowy `~/.ssh` tylko do odczytu (+ agent SSH, gdy `SSH_AUTH_SOCK` jest ustawiony) do push/pull |

Flagi łączą się: `orcan up --with-docker --with-git`.

Tożsamość **autora** Gita zawsze synchronizuje `orcan sync` (`GIT_AUTHOR_*` z hostowego `user.name` / `user.email`). Klucze SSH są podpinane tylko przez `--with-git`. Obie opcjonalne flagi wypisują ostrzeżenie bezpieczeństwa — agenci w środku mogą użyć zamontowanego socketa lub kluczy. Zobacz [Bezpieczeństwo](security.md) i [Workflowy](../guides/workflows.md).

## Make dla maintainerów

Z checkoutu gita: `make validate`, `make test-host`, `make docs*`, `make release*`, `make registry-*`. Zobacz [Development](../development/overview.md).
