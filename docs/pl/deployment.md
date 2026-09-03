# Wdrożenie

Jak instalować Orcan oraz jak publikowana jest **wersjonowana** dokumentacja.

## Runtime produktu (maszyna / VPS)

Orcan **nie** jest wdrażany jako obraz z GHCR.

### Kroki

1. Sklonuj tag release lub `main`
2. Skonfiguruj `orcan.config.json`
3. `orcan sync`
4. `orcan build --agent codex` (lub jawny wybór innego zestawu klientów)
5. `orcan up` (lokalnie — `orcan enter`) albo `orcan up --with-ttyd` (przeglądarka) albo `orcan up --with-docker | --with-network NAME` (wybierz jedno)

```bash
git clone https://github.com/aKyther/orcan.git
cd orcan
git checkout v0.1.0
orcan init /absolute/path/to/your/repo
orcan sync
orcan build --agent codex
orcan up
# zdalnie w przeglądarce: orcan up --with-ttyd && orcan url
```

### Wiele hostów

Na każdym hoście: `orcan build --agent codex` (albo `--all-agents`; build jest lokalny i nigdy nie publikuje). CI nie publikuje obrazów.

## Strona dokumentacji (wersje, mike)

Docs używają [mike](https://github.com/jimporter/mike) + selektora wersji Material, z angielskim i polskim w każdej wersji.

| Alias / wersja | Znaczenie | Typowy URL |
| --- | --- | --- |
| `latest` | Bieżący czubek `main` — domyślna strona lądowania | https://akyther.github.io/orcan/latest/ |
| `0.1.0` | Przypięty snapshot dla tego SemVer, z `make release` | https://akyther.github.io/orcan/0.1.0/ |
| `26.3` | Alias do tego samego snapshotu (etykieta CalVer) | https://akyther.github.io/orcan/26.3/ |
| `/` | Redirect do aliasu domyślnego (`latest`) | https://akyther.github.io/orcan/ |

`latest` oznacza tutaj „co jest teraz na `main`”, nie „ostatni release” —
patrz [Proces wydania](development/release.md) po pełny podział
`make tag` / `make release`. Strony PL: `/latest/pl/`, `/0.1.0/pl/` itd.

### Co publikuje co

| Zdarzenie Git | Akcja docs |
| --- | --- |
| Push tagu `vX.Y.Z` (z `make release`) | `mike deploy X.Y.Z` + alias `YY.Q` (workflow Release) — `latest` bez zmian |
| Push na `main` | `mike deploy` alias `latest` + set-default (CI) |
| Pull request | Tylko build/check — **bez** publish |

CI `docs-dev` i Release dzielą grupę concurrency `docs-gh-pages`, żeby nie pchać brancha jednocześnie. `docs-mike.sh` przed każdym deployem ponownie pobiera `gh-pages` i przy odrzuceniu pusha robi retry.

### Lokalne helpery mike

```bash
DOCS_MIKE_PUSH=0 make docs-mike-release
DOCS_MIKE_PUSH=0 make docs-mike-latest
./scripts/repository/docs-mike.sh list
```

W CI domyślnie `DOCS_MIKE_PUSH=1` (push `gh-pages`).

### Ustawienia Pages

GitHub → Settings → Pages → Deploy from branch → **`gh-pages`** / `(root)`.

Bez orphan wipe — mike trzyma wszystkie wersje na branchu.

### Wersja × język

Użyj **dropdownu wersji** w nagłówku razem z **Language**:

- **Dropdown wersji docs** — lista `latest`, folderów SemVer i ich aliasów `YY.Q` z
  [versions.json](https://akyther.github.io/orcan/versions.json). Działa na
  GitHub Pages **oraz** przy lokalnym `mkdocs serve` (pobiera opublikowany JSON).
  Przy przełączaniu zachowuje ścieżkę strony (np. Instalacja → ta sama strona na `2.0.0`).
- **Chip `vX.Y.Z`** — SemVer produktu z `extra.orcan_version`; link do Changelog.

Zagnieżdżone strony zachowują względne linki językowe; `mike-i18n.js` poprawia absolutne linki języka na stronie głównej pod `/latest/` i `/X.Y.Z/`.

Brak strony w starej wersji → często 404 lub home tej wersji.

## TODO

- [ ] Oficjalne pakowanie Helm / marketplace — nieplanowane
- [ ] Oficjalne obrazy GHCR — poza zakresem

## Zobacz też

- [Szybki start](getting-started/quickstart.md)
- [Proces wydania](development/release.md)
- [Docker](reference/docker.md)
- [Releases na GitHub](https://github.com/aKyther/orcan/releases)
