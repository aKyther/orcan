# Testy

## Kontrole hosta (szybkie — CI)

```bash
make validate
make test-host
make docs-check
```

| Target | Co robi |
| --- | --- |
| `make validate` | Wymagane pliki, składnia shell/Python, wersja pyproject, nazwa produktu, Compose `config` gdy Docker działa |
| `make test-host` | Testy jednostkowe config I/O, `apply-config`, wersja / release check, testy skryptów preview |
| `make docs-check` | Ścisły MkDocs (EN+PL) + kontrola nazwy produktu |

## Testy smoke (pełny obraz — lokalnie)

```bash
make test
```

Uruchamia `tests/smoke/test-container.sh` po `orcan build`. Oczekuje **pełnego** obrazu (obecny `agent`). Nie działa w CI (build obrazu jest za ciężki).

## Preview maintainerów (`scripts/dev/`)

Helpery lokalne w checkoutcie pod `scripts/dev/`. To **nie** jest publiczne CLI `orcan`. Preferuj cienkie wrappery `make dev-*`, żeby workflow testowy był łatwy do odkrycia **bez** ruszania codziennego zainstalowanego Orcana.

### Pełne developerskie środowisko przeglądarkowe — `orcan-preview`

Izolowany stack Docker z **tego** checkoutu: własny obraz, projekt Compose, home/data, port ttyd i kontener. Nie podmienia `orcan:latest` ani nie tyka `~/.config/orcan`.

```bash
make dev-start                           # build tylko gdy brakuje + start
# otwórz http://127.0.0.1:17681
make dev-restart                         # szybkie odświeżenie kodu z checkoutu
make dev-status
make dev-doctor                          # izolacja + health + HTTP + cockpit z checkoutu
make dev-smoke                           # prawdziwy Textual + tmux PTY
make dev-a11y                            # klawiatura/focus/axe (+ viewport 480x320)
make dev-visual                          # regresja screenshotów (900x700 / compact)
make dev-test                            # osobny lifecycle Docker; orcan-1 bez zmian
make dev-checklist                       # pre-merge (auto) + ręczny flow w przeglądarce
make dev-shell                           # shell w izolowanym preview
make dev-enter                           # launcher izolowanego środowiska developerskiego
make dev-stop                            # zachowaj obraz/cache
make dev-reset                           # stop + usuń domyślny stan fixture
```

| Cel Make | Komenda skryptu | Rola |
| --- | --- | --- |
| `dev-start` | `start [--port PORT\|auto]` | Start; build tylko gdy brakuje obrazu; wybiera wolny domyślny port |
| `dev-restart` | `restart [--port PORT\|auto]` | Odświeża cockpit z checkoutu i odtwarza kontener; czeka na healthy |
| — | `rebuild [--no-cache]` | Pełny rebuild dla zmian Dockerfile, rootfs lub zależności |
| `dev-status` | `status` / `url` | Health + URL |
| `dev-doctor` | `doctor` | Docker, tożsamość izolacji, health, HTTP, bind checkoutu, cockpit z checkoutu |
| `dev-visual` | — | Regresja screenshotów Chromium (`dev-ux.spec.js`; wymaga healthy preview) |
| `dev-visual-update` | — | Świadoma aktualizacja wzorców po przeglądzie |
| `dev-a11y` | — | Tab/focus, brak overflow, axe serious/critical, tiny `480x320` (`dev-a11y.spec.js`) |
| `dev-logs` | `logs` | Logi kontenera |
| `dev-shell` | `shell` | `orcan enter --shell` w kontenerze preview |
| `dev-enter` | `enter` | Izolowany launcher developerski |
| `dev-stop` | `stop` | Compose down (ze sprawdzeniem izolacji) |
| `dev-checklist` | `checklist` | Cele Make przed merge’em + ręczny flow (viewporty, axe, Alt/resize) |
| `dev-reset` | `reset` | Stop i usuń **tylko** domyślny `.orcan-dev-ux/` |
| `dev-test` | — | Osobny stack o unikalnej nazwie; assert że `orcan-1` bez zmian |
| — | `check` | Walidacja config/env; bez Dockera |

Domyślne (nadpisywalne):

| Element | Domyślnie |
| --- | --- |
| Fixture root | `.orcan-dev-ux/` (gitignored) w checkoutcie |
| Obraz | `orcan:dev-ux` |
| Kontener | `orcan-dev-ux` |
| Projekt Compose | `orcan-dev-ux` |
| Port ttyd na hoście | `17681` |
| Bind | `0.0.0.0` (LAN); `ORCAN_PREVIEW_BIND=127.0.0.1` tylko loopback |
| Scenariusz | `busy` |

Ustaw `ORCAN_PREVIEW_SCENARIO` (lub zmień zapisany `settings.env`), aby wybrać
fixture `orcan.config.json` generowany przez `write_fixture`:

| Scenariusz | Fixture zapisywany do `orcan.config.json` |
| --- | --- |
| `busy` | Domyślny — jeden workspace `dev-ux`, checkout jako jedyny projekt, 3 okna |
| `empty` | Jeden goły workspace `scratch`, jedno okno — niemal pusty cockpit |
| `long-names` | Bardzo długie nazwy workspace i projektu oraz drugi projekt, do testu zawijania / przycinania w railu |

Zmiana scenariusza jest stosowana przy kolejnym `start`/`restart`. Gdy zapisany
lub domyślny port jest zajęty, preview wybiera kolejny wolny; jawnie podany
zajęty port kończy się błędem. Mutujące operacje mają blokadę. Python cockpitu
jest ładowany bezpośrednio z checkoutu, więc zwykłe zmiany UX wymagają tylko
szybkiego `restart`; po zmianie Dockerfile, rootfs, lockfile lub zależności użyj
`rebuild`. Obraz zapisuje commit i stan `dirty` pokazywane po uruchomieniu.

Guardy izolacji odrzucają wartości kolidujące z normalną instalacją (`orcan:latest`, port `7681`, Compose `orcan`, instance `1`, prawdziwy `ORCAN_HOME`). `reset` odmawia przy niestandardowym `ORCAN_PREVIEW_ROOT`.

`make dev-test` uruchamia dodatkowy kontener o unikalnej nazwie, sprawdza
health, HTTP, path parity checkoutu, Textual i prawdziwy tmux PTY, usuwa go oraz
potwierdza, że ID `orcan-1` się nie zmieniło.

`make dev-visual` / `make dev-a11y` wymagają healthy preview (najpierw
`orcan-preview doctor`). Używają izolowanego kontenera Playwright
(`mcr.microsoft.com/playwright:v1.55.0-noble` domyślnie; nadpisz
`ORCAN_PLAYWRIGHT_IMAGE`), instalują `@playwright/test` + `@axe-core/playwright`
pod `.orcan-dev-ux/playwright-node/` i zapisują artefakty błędów w
`.orcan-dev-ux/artifacts/playwright/`. URL można nadpisać przez
`ORCAN_DEV_UX_URL`. Wzorce screenshotów leżą obok
`tests/browser/dev-ux.spec.js-snapshots/`.

`make dev-checklist` drukuje listę **Before merge (automated)**
(`dev-doctor`, `dev-smoke`, `dev-a11y`, `dev-visual`, `dev-test`) oraz ręczny
flow w przeglądarce (F4/F1, szczegóły workspace'a, wybór Enterem, Alt+1…9, resize, compact `900x700`, tiny
`480x320`, axe). Pakiet dostępności sprawdza też, że Tab dochodzi do terminala
i że viewport `480x320` zostawia użyteczny xterm.

!!! warning
    Domyślny bind to `0.0.0.0` (dostęp LAN). Nie uruchamiaj w niezaufanej sieci bez uwierzytelniania ttyd.

### Szybki chrome tmux — `terminal-ui-preview`

Bez Dockera. Uruchamia **izolowany serwer tmux** (osobny socket) z `docker/rootfs/etc/tmux/` z checkoutu. Normalny tmux Orcana zostaje nietknięty.

```bash
./scripts/dev/terminal-ui-preview              # attach; exit/detach sprząta
./scripts/dev/terminal-ui-preview --check      # status=2, 3 okna; bez attach
./scripts/dev/terminal-ui-preview --size 140x40
```

W preview: prefix **C-Space**; **C-Space r** przeładowuje pliki UI z checkoutu. Okna galerii ćwiczą krótkie/długie tytuły tabów i tiled pane’y.

To narzędzie na status / keybindings / layout. Na ttyd, launcher/cockpit albo pełny build obrazu — `orcan-preview`.

Testy hosta: `tests/host/test_orcan_preview.py`, `tests/host/test_terminal_ui_preview.py`.
Smoke cockpitu (w preview): `tests/smoke/test-cockpit-tui.py` przez `make dev-smoke`.
Przeglądarka: `tests/browser/dev-ux.spec.js` (`make dev-visual`), `tests/browser/dev-a11y.spec.js`
(`make dev-a11y`). Lifecycle izolacji: `tests/integration/test-dev-ux.sh` (`make dev-test`).

## Path parity

```bash
make test-path-parity
```

Wymaga Dockera i socketa hosta. Czyści się pomija, gdy niedostępne. Nie w CI.

## CI

GitHub Actions (`.github/workflows/ci.yml`) na `main` / PR:

1. `make validate`
2. `make test-host`
3. `make docs-check`
4. Przy pushu na `main`: `mike deploy` alias **`dev`**
5. Przy tagu `vX.Y.Z` (workflow Release): `mike deploy X.Y.Z` + alias **`latest`**

!!! warning
    CI **nie** buduje obrazów kontenera i **nie** uruchamia `make test`,
    `make test-path-parity` ani `make dev-*` / `dev-test` / `dev-visual`.
    Zielony PR oznacza validate + testy hosta + docs — nie zweryfikowany
    obraz ani UX przeglądarkowy. Uruchamiaj je lokalnie, gdy zmienia się
    Docker lub UX cockpitu.

URL docs: https://akyther.github.io/orcan/latest/ — zobacz [Wdrożenie](../deployment.md).

Wyszukiwanie PL używa angielskiego analizatora lunr (brak polskiego stemmera).

## Zobacz też

- [Przegląd rozwoju](overview.md)
- [Terminal UI](../guides/terminal-ui.md)
- [Proces wydania](release.md)
- [Referencja Makefile](../reference/makefile.md)
- [Path parity](../concepts/path-parity.md)
