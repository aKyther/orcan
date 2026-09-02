---
description: Typowe workflowy Orcana — najpierw scenariusze dnia, potem komendy CLI `orcan`.
---

# Typowe workflowy

Te scenariusze zakładają, że znasz już [Idee podstawowe](../ideas/core-ideas.md). Polecenia na **hoście**, o ile nie oznaczono **(kontener)**.

## Scenariusz: start dnia w jednym kontekście

Masz już skonfigurowane workspace'y. Chcesz kontener dev z wczorajszymi mountami.

**Idea:** odtwórz sesję bez regenerowania konfiguracji.

```bash
cd /absolute/path/to/orcan
orcan up              # lokalnie — orcan enter na tej samej maszynie
# zdalnie w przeglądarce: orcan up --with-ttyd && orcan url
```

!!! note
    `orcan up` **nie** uruchamia `orcan sync`. Jeśli zmieniłeś `orcan.config.json`, najpierw zastosuj konfigurację.

## Scenariusz: lokalny terminal (nie tylko przeglądarka) { #local-terminal }

**Kiedy:** jesteś na tej samej maszynie co kontener (laptop) i chcesz natywny terminal — albo drugi klient obok `--with-ttyd`.

Zwykłe `orcan up` to tryb lokalny (bez publikacji portu). **`orcan enter`** to domyślna ścieżka na tej samej maszynie. Dodaj **`--with-ttyd`**, gdy potrzebujesz przeglądarki (zdalnie / telefon).

```bash
orcan enter                 # cockpit: top bar + workspace'y | tmux + status
orcan enter --tmux          # lista sesji; attach jeśli jest tylko jedna
orcan enter --tmux my-ws    # attach do nazwanej sesji
orcan enter --shell         # zwykły zsh (bez tmux)

# równoważnie „nisko”:
docker exec -it orcan-1 tmux ls
docker exec -it orcan-1 agent-launcher
```

Alias: `orcan go-in` (to samo co `enter`). Domyślna nazwa kontenera to `orcan-1` (`ORCAN_INSTANCE`). Detach tmux: prefix + `d` — sesja dalej działa dla ttyd i innych klientów.

Gdy ttyd zerwie połączenie albo odświeżysz stronę, nowy proces cockpitu
automatycznie dołącza do ostatniego workspace'u. tmux odtwarza aktywne okno i
pane tej sesji. Wskazówka do ponownego połączenia jest tylko w `/tmp`, więc po
restarcie kontenera może wrócić lista workspace'ów; sesje tmux pozostają całe.

| Klawisze | Akcja |
| --- | --- |
| **F4** / pill workspace’a | Przełącz workspace’y; przypięte na szerokim ekranie, drawer na compact |
| **F5** | Peek briefu / następnej pending |
| **Klik `🌀 orcan`** | About (nazwa, wersja, docs) |
| **Klik bieżącego workspace’a** | Otwórz/zamknij listę workspace’ów |
| **F1** (zawsze) · **?** (poza terminalem) / rail ? | Overlay skrótów (nie About). Przy fokusie w terminalu użyj **F1** — **?** idzie do shella |
| **Ctrl+P** | Paleta komend (gdy fokus nie jest w terminalu) |
| **i** | Rozwiń/zwiń szczegóły workspace — root + repo (fokus na liście) |
| strzałki + Enter | Nawigacja / attach workspace (fokus na liście) |

W środkowym terminalu **działają skróty tmux** (prefix **C-Space**;
**Alt+1**…**Alt+9** wybiera okna; **prefix ?** otwiera samodzielny popup
skrótów tmux). Cockpit musi przekazywać te klawisze i resize do tmux — zobacz
[Terminal UI — Cockpit + przeglądarka](terminal-ui.md#cockpit-browser). **F1**
otwiera mapę w aplikacji, gdy fokus jest w terminalu (stopka: osadzony tmux ≠
native attach). Pełna mapa: `cockpit/…/shortcuts.py` (host testy trzymają ją w
sync z `keybindings.conf`).

!!! tip
    Przeglądarka + lokalny terminal mogą dzielić jedną sesję: edytuj w iTerm / Windows Terminal, trzymaj ttyd na telefonie lub drugim ekranie.

## Scenariusz: przełączenie klienta lub linii produktu

**Problem:** inny zestaw repo to dzisiejszy kontekst.  
**Podejście:** edytuj listę workspace'ów (lub włącz inny), zastosuj konfigurację, odtwórz kontener.

```bash
orcan init    # albo edytuj orcan.config.json
orcan sync
orcan down
orcan up
```

## Scenariusz: bezpieczniejszy terminal bez socketa Dockera hosta

**Kompromis:** brak Docker-from-Docker; mniejszy blast radius. To jest **domyślne**.

```bash
orcan up
```

## Scenariusz: terminal z socketem Dockera hosta (DinD)

**Kiedy:** zagnieżdżony Compose / Docker z wnętrza kontenera.

```bash
orcan up --with-docker
```

**Kompromis:** socket ≈ kontrola hostowego Docker Engine. Flaga jest świadomym
opt-inem (ostrzeżenie przy starcie). Nie ma trybu „pełny Docker hosta, ale
bezpieczny”. Jeśli wystarczy dojść do innych kontenerów — użyj
`--with-network` zamiast socketa. Szczegóły: [Bezpieczeństwo](../reference/security.md).

## Scenariusz: dojście do kontenerów na istniejącej sieci Docker

**Kiedy:** kontener ma sięgać innego kontenera po nazwie/IP (np. własny stack
`docker compose` projektu), ale nie musi sterować hostowym Dockerem.
Niższe ryzyko niż `--with-docker` — bez montowania socketa.

```bash
docker network create my-net   # jeśli jeszcze nie istnieje
orcan up --with-network my-net
```

## Scenariusz: git push/pull z kontenera

**Kiedy:** commity już mają tożsamość hosta (`orcan sync`); potrzebujesz też kluczy SSH lub agenta do remote'ów.

```bash
orcan up --with-git
# z DinD:
orcan up --with-docker --with-git
```

## Scenariusz: opcjonalny git worktree

**Kiedy:** chcesz drugi checkout bez ruszania klona od `main` / `pull`.

W wizardzie po podaniu ścieżki projektu odpowiedz **tak** na pytanie o worktree (domyślnie **nie** — samo montowanie).

Albo bez interakcji:

```bash
orcan context worktree create --repo /absolute/path/to/repo \
  --branch topic --workspace my-ws --project backend
orcan sync && orcan down && orcan up
```

Ścieżki managed: `$ORCAN_PROJECTS_ROOT/.worktrees/`. Sprzątanie: wizard → **clean**, albo `orcan context worktree remove --workspace my-ws`.

## Scenariusz: zainstaluj tylko jednego agenta

**Idea:** nie instaluj agenta, którego nie użyjesz (mniejszy obraz, te same tagi).

```bash
orcan build --claude   # → orcan:<VERSION>-claude
IMAGE_LOCAL=orcan:0.1.1-claude orcan up
# albo
orcan build --cursor   # → orcan:<VERSION>-cursor
IMAGE_LOCAL=orcan:0.1.1-cursor orcan up
```

## Scenariusz: rebuild po zmianach Dockerfile lub rootfs

**Idea:** opis kontekstu ten sam; zmienił się **obraz narzędzi**.

```bash
orcan build --force       # pełny obraz; pomiń pull, zbuduj lokalnie
# albo
orcan build --claude --force
orcan down
orcan up
```

## Scenariusz: weryfikacja path parity

**Dlaczego:** zagnieżdżony Docker działa tylko przy zgodnych ścieżkach bezwzględnych.

```bash
orcan context show
```

## Wewnątrz kontenera

| Potrzeba | Polecenie |
| --- | --- |
| Lista workspace'ów | `orcan-workspaces` |
| Seed wszystkich projektów | `orcan-init-projects` |
| Session brief | `orcan-session-brief` |
| Helper statusu AI | `orcan-ai-statusline` |
| Cursor CLI | `agent` / `ag` |
| Claude Code | `claude` / `cc` |

Klawisze launchera: numer workspace'a, `s` = status, `i` = wskazówka init, `q` = wyjście.

## Stop, czyszczenie, odinstalowanie

```bash
orcan down                 # zatrzymaj; zachowaj ~/.config/orcan
orcan uninstall                         # usuń runtime + CLI; zachowaj dane/projekty/obrazy
orcan uninstall --purge-data            # usuń też config/loginy/cache; zachowaj projekty
orcan uninstall --purge-images          # usuń też lokalne tagi obrazów orcan:*
```

Pełne usunięcie: [Odinstalowanie](#uninstall).

## Odinstalowanie { #uninstall }

```bash
orcan uninstall --purge-data --purge-images
```

Komenda prosi o wpisanie `yes`, zatrzymuje warianty Compose Orcana oraz usuwa
launcher i standardowy klon instalatora. Checkout developerski jest raportowany
i zostaje. `--purge-data` usuwa zawartość `ORCAN_HOME`/`ORCAN_DATA`, ale chroni
cały `ORCAN_PROJECTS_ROOT` i skonfigurowane ścieżki projektów. Przy domyślnym
układzie `~/.config/orcan/sandbox` zostaje. `--purge-images` celuje tylko w
lokalne tagi `orcan:*`; obraz używany przez inny kontener zostaje z raportem.

!!! warning

    Granica ochrony pochodzi z `$ORCAN_HOME/.env` i bieżącego
    `orcan.config.json`. Nie trzymaj niezarejestrowanych repo w innym miejscu
    pod `ORCAN_DATA`. Uszkodzony config albo niebezpieczny/symlinkowany root
    danych zatrzymuje purge zamiast zgadywać.

## Aktualizacja / downgrade Orcana

```bash
cd /absolute/path/to/orcan
orcan upgrade                # najnowszy tag GitHub Release (vX.Y.Z)
# orcan upgrade --to v0.2.0  # przypnij konkretny release (w górę lub w dół)
# orcan update                # kanał dev: zamiast tego śledź main
orcan downgrade              # jeden krok SemVer wstecz (escape hatch po złym release)
# orcan downgrade --to v0.1.0
orcan sync                   # gdy zmienił się schemat konfiguracji
orcan build --force          # gdy zmienił się Dockerfile/rootfs
orcan down && orcan up
```

## Zobacz też

- [Szybki start](../getting-started/quickstart.md)  
- [Rozwiązywanie problemów](troubleshooting.md)  
- [Referencja CLI](../reference/cli.md)  
- [FAQ](../faq.md)
