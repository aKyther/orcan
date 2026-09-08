---
description: Wygląd terminala — stonowany grafitowo-śliwkowy chrome wokół narzędzi terminalowych. Gdzie edytować i jak rozszerzać.
tags:
  - guide
  - develop
---

# Terminal UI

Cockpit Orcana używa spokojnych powierzchni **grafit / prawie czarny /
stonowana śliwka**. Jeden fioletowy akcent oznacza interakcję; pozostałe
kolory są zarezerwowane dla stanu. Chrome tmux używa tej samej hierarchii,
a programy wewnątrz paneli zachowują własną paletę terminalową. Ta strona to
mapa dla ludzi i agentów zmieniających ten stack.

## Stack

```text
ttyd (motyw xterm.js) → tmux 3.6a → zsh
  ├── prompt Starship
  ├── zsh-autosuggestions + syntax-highlighting + fzf
  ├── aliasy (/etc/orcan/shell/aliases.sh)
  └── lazygit / delta (UI gita)
```

Ograniczenia (nie łamać):

- **ttyd-safe** — Menlo / Monaco / Courier; **bez wymogu Nerd Font**
- Zwykłe Unicode w statusie tmux (bez glifów Powerline)
- Defaulty obrazu w `docker/rootfs/`; nadpisania w `$ORCAN_DATA/dotfiles`

Osadzony PTY Cockpitu rysuje migający kursor typu reverse-video, gdy ma fokus
klawiatury. Śledzi kursor z zsh, Codexa, Claude Code i innych aplikacji
terminalowych, ale respektuje programy, które celowo go ukrywają.

## Paleta

| Rola | Hex | Użycie |
| --- | --- | --- |
| Tło | `#12101a` | cockpit i puste stany |
| Podniesione | `#1b1724`, `#211c2b` | paski, picker, dialogi |
| Zaznaczenie | `#2a2237`, `#342a44` | aktywne i wskazane powierzchnie |
| Tekst | `#e2ddea` | główny tekst |
| Wyciszony | `#948ba3`, `#b0a6ba` | metadane i tekst drugorzędny |
| Akcent | `#ad91d0`, `#c7b1e2` | fokus i interaktywna tożsamość |
| Ostrzeżenie / błąd | `#fbbf24`, `#f87171` | activity, błędy, niska bateria |

**Site MkDocs** używa tych samych tokenów (`docs/assets/stylesheets/orcan.css`, favicon). W jasnym trybie docs — ciemniejszy teal dla czytelnych linków na białym.

Presety w `cursor-ttyd`:

| `TTYD_THEME` / `ttyd.theme` | Znaczenie |
| --- | --- |
| `dark` lub `navy` (domyślne) | Paleta grafit/śliwka (stara nazwa presetu) |
| `mocha` / `catppuccin` | Stary Catppuccin Mocha |
| surowy JSON `{...}` | Własny motyw xterm.js |

## Gdzie zmieniać co

| Warstwa | Ścieżka w repo | Jak wdrożyć |
| --- | --- | --- |
| motyw ttyd | `docker/rootfs/usr/local/bin/cursor-ttyd` | `orcan build` + recreate kontenera |
| binarka tmux | `Dockerfile` (`ARG TMUX_VERSION=3.6a`) | build — static z `tmux/tmux-builds` |
| UI tmux | `docker/rootfs/etc/tmux/` | build; albo kopia + `tmux source-file` przy iteracji |
| Layout / chrome cockpit | `cockpit/src/orcan_cockpit/app.py`, `top_bar.py`, `rail.py`, `status_bar.py` | `make dev-restart` (izolowane); albo `orcan build` + recreate |
| Skróty / help cockpit | `cockpit/…/shortcuts.py` (+ `keybindings.conf` dla tokenów tmux) | j.w.; test hosta trzyma tokeny w sync |
| PTY cockpit | `pty_terminal.py`, `pty_keys.py`, `pty_colors.py`, `pty_tmux_nav.py` | j.w. — zobacz [Cockpit + przeglądarka](#cockpit-browser) / [nav mix](#cockpit-nav-mix) |
| zsh | `docker/rootfs/etc/skel/.zshrc`, `.zshrc.d/` | build; albo kopia do `~` na test na żywo |
| kolory fzf / suggest | `docker/rootfs/etc/skel/.zshrc.d/70-plugins.zsh` | nowy shell po kopii/buildzie |
| Starship | `docker/rootfs/opt/orcan/starship.toml` | zarządzany default → `~/.config/starship.toml` |
| lazygit | `docker/rootfs/opt/orcan/lazygit-config.yml` | zarządzany default → `~/.config/lazygit/config.yml` |
| git / delta | `docker/rootfs/opt/orcan/gitconfig` | missing-only → `~/.gitconfig` |
| Overlay użytkownika | `$ORCAN_DATA/dotfiles` | montowane; zobacz [Dotfiles](dotfiles.md) |

Starship i lazygit używają **zarządzanych defaultów**: Orcan zapisuje dokładny
seed, który skopiował, i odświeża go przy kolejnym obrazie tylko dopóki plik nie
został zmieniony. Znane defaulty ze starszych obrazów są migrowane raz na
podstawie sumy kontrolnej. Edycja użytkownika lub overlay dotfiles zatrzymuje
zarządzanie i nigdy nie jest nadpisywany. Git config pozostaje missing-only.

## tmux (3.6a)

### Bindings z prefixem (po `C-Space`)

| Klawisze | Akcja |
| --- | --- |
| `r` | Przeładuj `/etc/tmux/tmux.conf` |
| `s` / `w` | Przełącz sesję workspace orcan |
| `W` | Wybór okna (jak IDE) |
| `u` | Wybierz/skopiuj URL http(s) (łączy soft-wrap) |
| `P` | Helper kopiowania ścieżki |
| `-` / `\|` | Split pionowy / poziomy |
| `x` | Zabij pane |

### Bez prefixu (Meta / Alt — lokalne skróty)

Używają bindów tmux `M-…` / `C-…` w `keybindings.conf` dla **surowego**
`orcan enter --tmux`. Muszą dojść jako **Meta**/CSI Ctrl, nie jako znaki
złożone. **W cockpicie** strzałki działają inaczej — zobacz
[Cockpit nav mix](#cockpit-nav-mix).

| Klawisze | Akcja (`--tmux` / conf) |
| --- | --- |
| `Alt+1` … `Alt+9` | Wybór okna 1–9 |
| `Alt+0` | Ostatnie okno |
| `Alt+←/→/↑/↓` | Fokus pane |
| `prefix z` | Zoom pane |
| `Alt+c` | Nowe okno |
| `Alt+a` / `Alt+q` | Mysz włącz / wyłącz |
| `Ctrl+←/→/↑/↓` | Split (kierunek) |
| `Ctrl+Alt+←/→` | Poprzednie / następne okno |
| `Ctrl+Shift+←/→` | Zamień okno w lewo / prawo |

### Cockpit + przeglądarka (nie psuć) { #cockpit-browser }

Gdy `agent-launcher` osadza tmux (`cockpit/…/pty_terminal.py`):

#### Dwa terminale w jednym

Osadzony tmux **nie jest** natywnym attach (`tmux attach` w Windows Terminal).
Overlay skrótów cockpit (**F1** zawsze; **?** gdy fokus poza osadzonym
terminalem) oraz popup tmux **prefix ?** powtarzają to na dole —
zobacz `EMBED_DISCLAIMER` w `shortcuts.py`. Przy fokusie w terminalu **?** idzie
do shella — użyj tam **F1**. To trzy warstwy naraz:

```text
Textual (UI, fokus, selekcja, mysz)  ↔  pyte (emulacja VT100)  ↔  tmux attach (PTY)
```

Textual **nie** przekazuje klawiatury/myszy/sklejki automatycznie — każdy kanał
wymaga własnego tłumacza w repo. To oczekiwane, nie bug pojedynczej funkcji.
Przy `make dev-enter` / cockpicie zakładaj, że **każdy nowy input** (scroll,
copy, klik w status tmux, bracketed paste, …) może wymagać osobnej logiki —
albo użyj pełnego tmux: `orcan enter --tmux NAZWA` (bez cockpitu).

| Moduł | Kierunek | Problem bez tłumacza |
| --- | --- | --- |
| `pty_tmux_nav.py` | Textual → `tmux` CLI | Ctrl/Alt+strzałki / Ctrl+Shift+strzałki — zob. [Cockpit nav mix](#cockpit-nav-mix) |
| `pty_keys.py` | Textual → PTY | pozostałe ``bind -n`` z `keybindings.conf` — patrz tabela poniżej |
| `pty_mouse.py` | Textual → PTY | wheel/klik nie dociera; SGR vs legacy X10 (`@`/`A` na ekranie) |
| `pty_colors.py` | pyte → Rich | `brown` / bright aliasy psują render |
| `pty_terminal.py` | PTY ↔ pyte ↔ UI | resize (`TIOCSCTTY`), odświeżanie, selekcja vs tmux, tryby `?1000/1006`, sklejanie `Escape`+klawisz |

#### Cockpit nav mix (limit Alt-jako-Ctrl) { #cockpit-nav-mix }

**Ograniczenie:** pod ttyd/xterm.js i w części terminali desktop (Windows Terminal /
WSL) **Alt+←/→/↑/↓** często dociera do Textual jako **`ctrl+arrow`** — nie ma
osobnego eventu Meta. Cockpit nie może jednocześnie oferować „Ctrl = split” i
„Alt = fokus pane”, gdy te chordy wyglądają tak samo.

**Zachowanie cockpitu** (`pty_tmux_nav.py` — wywołuje `tmux select-pane` /
`split-window` bezpośrednio, bez CSI do child PTY):

| Skrót | Akcja w cockpicie |
| --- | --- |
| `Ctrl` lub `Alt` + `←/→/↑/↓` | Fokus pane |
| `Ctrl+Shift` + `←/→/↑/↓` | Split pane |
| `prefix -` / `prefix \|` | Split (bez zmian; forward do tmux) |

**Surowy attach** (`orcan enter --tmux`): `keybindings.conf` bez zmian —
`Ctrl+strzałki` = split, `Alt+strzałki` = fokus **gdy Meta dochodzi**.

Stopki F1 / **?** oraz **prefix ?** pokazują to jako `BROWSER_KEY_LIMIT` w
`shortcuts.py`. `Alt+1`…`Alt+9` to osobna ścieżka (często OK z
`macOptionIsMeta` na macOS).

**Lokalne bindy tmux (`bind -n`, bez prefixu)** — nadal dla chordów, które
cockpit **forwarduje** jako bajty (nie zestaw nav-mix powyżej). Każdy wymaga
poprawnego CSI / Meta w jednym write:

| Skrót | tmux | Bajty (docelowo) |
| --- | --- | --- |
| `Ctrl+Space` | prefix | `\x00` |
| `prefix z` | zoom pane | `z` po `\x00` (C-Space) — bez mapy w wrapperze |
| `Ctrl+Alt+←/→` | prev/next window | `\x1b[1;7D/C` |
| `Alt+c` / `Alt+a` / `Alt+q` | new win / mouse | `\x1bc` / `\x1ba` / `\x1bq` |
| `Alt+0..9` | select window | `\x1b0` … `\x1b9` |

Textual rozbija wiele z powyższych na `Escape` + drugi klawisz — cockpit skleja z powrotem (`pty_keys.esc_follow_up_bytes` + okno coalesce w `pty_terminal`).

**Mysz:** tmux wysyła `?1006l` potem `?1006h` przy attach — parser musi brać
**ostatni** stan (nie `in data`). Inaczej leci legacy encoding i w shellu widać
`A_5`, `@_5`. Wysyłaj zdarzenia myszy dopiero gdy tmux włączy `?1000h`.

**Kopiowanie:** zaznaczenie to selekcja Textual (nie xterm). `Ctrl+C` z
zaznaczeniem → schowek; bez zaznaczenia → SIGINT. Potwierdzone duże wklejki
są kolejkowane do nieblokującego PTY, więc cały tekst dociera mimo ograniczenia
bufora PTY.

Wklejki od **32 KiB** nie są wpisywane bezpośrednio do aktywnego agenta.
Orcan zapisuje prywatny plik `0600` pod `/tmp/orcan-paste-*.md` i wpisuje krótką
instrukcję z jego ścieżką. Agent może przeczytać pełną prośbę bez zalewania TTY;
pliki wygasają po 24 godzinach.

**Scrollback:** pyte trzyma **bieżący** ekran; przewijanie historii robi tmux
(copy-mode) i przerysowuje pane — mysz musi trafić do tmux jako SGR.

**Scrollback:** pyte trzyma **bieżący** ekran; przewijanie historii robi tmux
(copy-mode) i przerysowuje pane — mysz musi trafić do tmux jako SGR.

#### Konkretne wymagania (regresja)

- **`C-Space` i `Alt+…` muszą dojść do tmux** — widget mapuje klawisze Textual na bajty pty (`ctrl+space` → `\x00`; `alt+1` → jeden zapis `\x1b` + `1`). Rozdzielenie ESC i klawisza bazowego na dwa write’y psuje `escape-time` (tmux traktuje ESC osobno). Textual mapuje też `ESC+digit` na glify macOS Option (`¡`/`™`/`£`); cockpit odwraca to z powrotem na Meta (`pty_keys.py`), żeby Windows Terminal / Linux Alt+1…9 działało jak przy zwykłym `tmux attach`.
- **Resize** wymaga controlling tty w childzie (`TIOCSCTTY`), żeby `TIOCSWINSZ` dostarczył **SIGWINCH** do tmux — inaczej pane zostaje przy rozmiarze z attach.
- Przy spawnie, gdy widget ma jeszcze `0×0`, fallback to **80×24** (unika martwego 1×1).
- Kolory: render per-cell pyte (status/prompt jak przy native attach).

Testy hosta (bez Textual): `tests/host/test_cockpit_pty_{keys,mouse,colors,tmux_nav}.py`.
Smoke: `tests/smoke/test-cockpit-tui.py`.

Browser ttyd (`cursor-ttyd`) ustawia **`macOptionIsMeta=true`**, żeby na macOS Option/Alt szło jako Meta (potrzebne do `Alt+1`…), a nie jako `¡` / `™`. Bez wpływu na Windows/Linux.

Na ekranach dotykowych pionowe przeciągnięcie jednym palcem nad osadzonym
terminalem przewija historię tmuxa. Most reaguje tylko na zdarzenia dotykowe
przeglądarki; mysz, touchpad, klawiatura, natywne `orcan enter` oraz Windows
Terminal / WSL zachowują dotychczasowe ścieżki wejścia. Krótkie dotknięcie
pozostaje tapnięciem, ponieważ przewijanie zaczyna się dopiero po przekroczeniu
progu ruchu w pionie.

Typografia telefonu i tabletu jest responsywna: 16 px do szerokości 600 px,
14 px do 1024 px oraz skonfigurowane `TTYD_FONT_SIZE` (domyślnie 14 px) na
desktopie. Jawny parametr URL `?fontSize=N` ma pierwszeństwo przed profilem
automatycznym, także gdy dodasz go do wcześniej adaptacyjnego URL. Gdy input
xterm ma fokus, most śledzi też `visualViewport`;
kiedy klawiatura ekranowa zmniejsza widoczną wysokość, ttyd dopasowuje liczbę
wierszy tak, aby bieżący prompt pozostał nad klawiaturą.

`ttyd.renderer` wybiera renderer xterm: domyślny **`webgl`** jest szybki przy
scrollowaniu i dużym wyjściu, a **`canvas`** jest fallbackiem dla przeglądarki
lub GPU, które źle rysują glify WebGL. Przeglądarka bez WebGL automatycznie
przechodzi na canvas. Otwórz URL terminala z `?orcanDiagnostics=1` (adres jest
też w `orcan doctor`), aby zobaczyć preferencję renderera, device-pixel ratio,
zoom, rozpoznany font, rozmiar canvasa i powód fallbacku. Przy ocenie ostrości
tekstu ustaw zoom przeglądarki na 100%; ułamkowe skalowanie przeglądarki lub
systemu może zmiękczać tekst canvasa.

### Chrome cockpitu (warstwa app)

**Progi szerokości** (kolumny terminala, nie breakpointy CSS — `status.py` /
`tier_for_width`):

| Tier | Kolumny | Efekt |
| --- | --- | --- |
| `compact` | 90–119 | Krótszy dolny pasek; picker workspace’a nakłada się na terminal |
| `minimal` | < 90 | Przed podłączeniem zachowuje chrome pickera. Po podłączeniu przechodzi w tryb terminal-first: zostaje tylko dyskretny pill workspace’a, a tmux odzyskuje wiersze identity i statusu. F4 nadal otwiera picker jako overlay bez zmiany rozmiaru tmuxa. |

Górny pasek zostawia tylko kontekst workspace’a i spokojny zegar. Obciążenie
CPU oraz pamięć są dostępne po najechaniu na zegar, zamiast stale konkurować
z terminalem. Picker pokazuje najpierw ostatnio podłączane workspace’y, a
pozostałe zachowują kolejność z konfiguracji.

Przy fokusie pickera zacznij pisać, aby filtrować po nazwie workspace’a,
sesji lub root; **Backspace** poszerza listę ponownie. **`i`** nadal otwiera
szczegóły, a **`?`** skróty, więc filtr zaczynający się od tych znaków rozpocznij
od **`/`**.

Naciśnij **Ctrl+C** w pickerze, aby skopiować root zaznaczonego workspace’a.
W terminalu Ctrl+C zachowuje zwykłe działanie kopiowania zaznaczenia / przerwania.

Po rozwinięciu szczegółów (`i`) kliknij projekt w żywym workspace’ie, aby
otworzyć tam nowy pane tmuxa. Bieżący pane agenta i jego katalog nie zmieniają się.

| Klawisze | Akcja |
| --- | --- |
| **F4** / pill workspace’a | Otwórz picker workspace’a bez zmiany rozmiaru terminala |
| **F6** | Przełącz na ostatnio używany inny workspace; kolejne użycie przełącza między dwoma ostatnimi |
| **`i`** (picker) | Pokaż lub ukryj root, Git/worktree/projekty i glance żywej sesji zaznaczonego workspace’a; domyślnie picker jest krótką listą decyzji |
| **Wskaźnik fokusu** | Fioletowa krawędź i etykieta obszaru na dolnym pasku mówią, czy klawisze trafiają do Terminala, Workspace’ów czy Controls |
| **F1** (zawsze) · **?** (poza terminalem) / rail ? | Overlay skrótów (nie About). Przy fokusie w terminalu **?** idzie do shella — użyj **F1** |
| **Klik `🌀 orcan`** | About (nazwa, wersja, docs) — zamknij **Enterem** albo widocznym przyciskiem **Close**; `about_modal.py` |
| **Exit** (górny pasek) | Zamknij Cockpit i wróć do terminala hosta; sesje tmux dalej działają |

Przed podłączeniem terminala środek pokazuje jeden spokojny kolejny krok:
wybierz workspace pill-em albo **F4**. Podaje liczbę gotowych workspace’ów, a
gdy nie ma żadnego, kieruje wprost do `orcan init`.

Zmiana workspace’a zostawia krótki stan przejścia pośrodku podczas odtwarzania
tmuxa. Gdy otwarcie się nie uda, kliknij zwięzły komunikat błędu (albo użyj
**F4**), aby wrócić do pickera; poprzednia tożsamość workspace’a jest czyszczona.

About, skróty i brief sesji używają tego samego tymczasowego sheetu: widoczny
przycisk **Close** działa obok ich skrótów klawiaturowych. Na telefonie sheet
wypełnia ekran zamiast zamieniać się w przycięty dialog desktopowy.

Krótkie komunikaty Cockpitu pojawiają się jako możliwy do kliknięcia toast w
prawym dolnym rogu, nad tmuxem; znikają automatycznie i nigdy nie zmieniają
rozmiaru terminala. Stonowana fioletowa, bursztynowa lub różana krawędź
rozróżnia informację, ostrzeżenie i błąd.

Gdy aktywny pane tmuxa uruchamia rozpoznane CLI programistyczne, pill
workspace’a dostaje małą kropkę i nazwę (na przykład `• Codex`). To wskaźnik
procesu, nie deklaracja, że agent właśnie generuje odpowiedź: CLI czekające na
input nadal jest procesem CLI.

Paleta komend **Ctrl+P** używa tej samej spokojnej powierzchni sheeta: wpisz
filtr, użyj strzałek i **Entera**, aby wykonać akcję, albo kliknij poza nią,
aby ją zamknąć.
| **Klik bieżącego workspace’a** | Otwórz/zamknij listę bez utraty informacji o aktywnym workspace’ie |
| **F5** | Podejrzyj session brief bieżącego workspace’a |
| **Ctrl+P** | Paleta komend (poza fokusem terminala) |
| **i** | Rozwiń/zwiń szczegóły workspace (fokus na liście) |
| **prefix ?** | Samodzielny popup skrótów tmux (bez cockpitu) |
| **`lg`** (w shellu) | lazygit — nie F-key w cockpicie |

Codzienne wejście: [Workflowy — lokalny terminal](workflows.md#local-terminal).

Po edycji UX: `make dev-restart`, potem `make dev-smoke` (oraz `make dev-visual`, gdy ważne są screenshoty layoutu/chrome); spróbuj `Alt+1` / resize okna przeglądarki; albo `./scripts/dev/terminal-ui-preview` tylko na chrome.

## Preview bez ruszania codziennego Orcana

Z checkoutu gita (nie publiczne CLI):

| Potrzeba | Komenda | Uwagi |
| --- | --- | --- |
| Tylko status / klawisze / layout tmux | `./scripts/dev/terminal-ui-preview` | Osobny socket tmux; **C-Space r** przeładowuje pliki z checkoutu |
| Pełny UX przeglądarkowy (ttyd + cockpit + obraz) | `make dev-start` | Obraz `orcan:dev-ux`, port/home pod `.orcan-dev-ux/` |
| Po edycji UX | `make dev-restart` | Odśwież cockpit z checkoutu; recreate; czeka na healthy |
| Automatyczne checki | `make dev-smoke` / `dev-a11y` / `dev-visual` | Textual+PTY; Playwright a11y + screenshoty (preview musi działać) |
| Lista przed merge’em | `make dev-checklist` | Cele automatyczne + ręczny flow w przeglądarce |
| Weryfikacja izolacji | `make dev-doctor` | Tożsamość Dockera, health, HTTP |

Szczegóły, flagi i reguły izolacji: [Testy — preview maintainerów](../development/testing.md).

## Rozszerzanie wyglądu (checklist dla agentów)

1. Wybierz wiersz z tabeli; edytuj ścieżkę w **repo**.
2. Trzymaj spójne hexy palety (albo zaktualizuj ten doc + wszystkie warstwy naraz).
3. **Nie** dodawaj TPM / Catppuccin-tmux / Oh My Zsh / Powerlevel10k bez decyzji produktowej.
4. Iteruj przez `./scripts/dev/terminal-ui-preview` (tmux) albo `make dev-restart` (pełny UX); weryfikuj `make dev-smoke` / `make dev-visual` w razie potrzeby.
5. Zaktualizuj docs **EN + PL** i `CHANGELOG.md` `[Unreleased]`.
6. `make validate` i `make docs-check`.
7. Dla Dockerfile / rootfs w obrazie: `orcan build && orcan down && orcan up`.

Reguła Cursora (gdy ruszasz te ścieżki): `.cursor/rules/terminal-ui.mdc`.

## Powiązane

- [Dotfiles użytkownika](dotfiles.md) — własne nadpisania bez rebuilda
- [Testy](../development/testing.md) — `make dev-*` / `scripts/dev/`
- [Docker — referencja](../reference/docker.md) — zawartość obrazu, tmux 3.6a
- [Zmienne środowiskowe](../reference/environment.md) — `TTYD_THEME`, fonty
- [Kontekst AI](../ai/project-context.md) — rytuał agenta
