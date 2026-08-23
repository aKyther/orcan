# Wdrożenie

Jak instalować Orcan oraz jak publikowana jest **wersjonowana** dokumentacja.

## Runtime produktu (maszyna / VPS)

Orcan **nie** jest wdrażany jako obraz z GHCR.

### Kroki

1. Sklonuj tag release lub `main`
2. Skonfiguruj `orcan.config.json`
3. `orcan sync`
4. `orcan build` (lub `orcan build --claude`)
5. `orcan up` (lokalnie — `orcan enter`) albo `orcan up --with-ttyd` (przeglądarka) albo `orcan up --with-docker | --with-network NAME` (wybierz jedno)

```bash
git clone https://github.com/aKyther/orcan.git
cd orcan
git checkout v0.1.0
orcan init /absolute/path/to/your/repo
orcan sync
orcan build
orcan up
# zdalnie w przeglądarce: orcan up --with-ttyd && orcan url
```

### Wiele hostów

Na każdym hoście: `orcan build` (pull pasującej `VERSION`, albo lokalny build przy braku — nigdy nie publikuje). CI nie publikuje obrazów.

## Strona dokumentacji (wersje, mike)

Docs używają [mike](https://github.com/jimporter/mike) + selektora wersji Material, z angielskim i polskim w każdej wersji.

| Alias / wersja | Znaczenie | Typowy URL |
| --- | --- | --- |
| `latest` | Ostatni **release** (git tag) | https://akyther.github.io/orcan/latest/ |
| `0.1.0` | Snapshot SemVer | https://akyther.github.io/orcan/0.1.0/ |
| `dev` | Tip `main` (nieopublikowane) | https://akyther.github.io/orcan/dev/ |
| `/` | Redirect do aliasu domyślnego (`latest`) | https://akyther.github.io/orcan/ |

Strony PL: `/latest/pl/`, `/0.1.0/pl/` itd.

### Co publikuje co

| Zdarzenie Git | Akcja docs |
| --- | --- |
| Push tagu `vX.Y.Z` | `mike deploy X.Y.Z` + alias `latest` + set-default (workflow Release) |
| Push na `main` | `mike deploy` alias `dev` (CI) |
| Pull request | Tylko build/check — **bez** publish |

CI `docs-dev` i Release dzielą grupę concurrency `docs-gh-pages`, żeby nie pchać brancha jednocześnie. `docs-mike.sh` przed każdym deployem ponownie pobiera `gh-pages` i przy odrzuceniu pusha robi retry.

### Lokalne helpery mike

```bash
DOCS_MIKE_PUSH=0 make docs-mike-release
DOCS_MIKE_PUSH=0 make docs-mike-dev
./scripts/repository/docs-mike.sh list
```

W CI domyślnie `DOCS_MIKE_PUSH=1` (push `gh-pages`).

### Ustawienia Pages

GitHub → Settings → Pages → Deploy from branch → **`gh-pages`** / `(root)`.

Bez orphan wipe — mike trzyma wszystkie wersje na branchu.

### Wersja × język

Użyj kontrolek **Version** i **Language** w nagłówku. Skrypt `mike-i18n.js` poprawia absolutne linki języka na stronie głównej pod `/latest/` i `/X.Y.Z/`.

Brak strony w starej wersji → często 404 lub home tej wersji.

## TODO

- [ ] Oficjalne pakowanie Helm / marketplace — nieplanowane
- [ ] Oficjalne obrazy GHCR — poza zakresem

## Zobacz też

- [Szybki start](getting-started/quickstart.md)
- [Proces wydania](development/release.md)
- [Docker](reference/docker.md)
- [Releases na GitHub](https://github.com/aKyther/orcan/releases)
