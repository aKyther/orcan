# Proces wydania

## Trzy poziomy (krótko)

| Co robisz | Docs / produkt |
| --- | --- |
| PR → merge do `main` | Aktualizuje się alias docs **`latest`** (bieżący czubek main). Bez nowego taga. Bez GitHub Release. |
| `make tag` — Twój checkpoint | Podbija SemVer, przenosi `[Unreleased]` w `CHANGELOG.md` do `[X.Y.Z]`, commit + tag, **w pełni pushowane** — ale tag żyje pod `checkpoint/vX.Y.Z`, nie gołym `vX.Y.Z`, więc nie może odpalić release'u ani stać się celem update'u. |
| `make release` — właściwy, świadomy stop | Upewnia się, że istnieje realny, pushnięty goły tag `vX.Y.Z`, dokłada własny tag CalVer (`26.3`) na tym samym commicie, separator w CHANGELOG nad wszystkim, co się nazbierało od ostatniego release'u, GitHub Release, snapshot docs `X.Y.Z` (+ alias `26.3`). |

`latest` = „co jest teraz na main” (rolling — zastępuje dawną nazwę aliasu `dev`).
Numerowane snapshoty docs (`X.Y.Z`, `26.3`) powstają wyłącznie przy realnym `make release`.

Zwykłe commity robocze — również te wypychane tylko po to, by coś przetestować
na innym komputerze — nigdy nie ruszają wersji ani tagów. Robią to wyłącznie
`make tag` / `make release`, i tylko wtedy, gdy sam(a) o tym zdecydujesz.

## Model

- SemVer w `cockpit/pyproject.toml` (`version = "X.Y.Z"`; root `VERSION` to zsynchronizowane lustro). Goły tag git `vX.Y.Z` to na czym opierają się `orcan update`/`orcan downgrade`, CI i GitHub Releases — tworzy go wyłącznie `make release`.
- Tagi checkpointów (`checkpoint/vX.Y.Z`, z `make tag`) to osobna przestrzeń nazw. `orcan update`/`downgrade` dopasowują tylko `^v[0-9]+\.[0-9]+\.[0-9]+$`, a `release.yml` odpala się tylko na `v*.*.*` — żadne z nich nie dopasuje tagu `checkpoint/...`, więc checkpointy są w pełni pushowane i widoczne na GitHubie, nigdy nie będąc kandydatem na release/update.
- CalVer (`YY.Q`, np. `26.3`) dostaje przy release'ie własny, goły tag — „wszystko stąd dotąd to release 26.3” — plus separator `## YY.Q — DATA` w `CHANGELOG.md`, dodatkowy alias w `mike`, tytuł GitHub Release. To drugi, nazwany po ludzku wskaźnik na ten sam commit co tag `vX.Y.Z` release'u, nie jego zamiennik.
- Wersjonowane docs przez **mike**: `latest` (rolling), `X.Y.Z` (każdy release), `YY.Q` (alias do tego samego release'u).
- **Brak** publikacji obrazu kontenera z CI.
- Użytkownicy: `git checkout vX.Y.Z && orcan build`.

## Checkpoint — `make tag`

Uruchamiaj, kiedy uznasz, że paczka commitów (1 czy 50 — bez znaczenia)
jest gotowa i chcesz mieć stabilny punkt do powrotu. Wymaga czystego
drzewa (najpierw zacommituj swoją pracę).

```bash
make tag                # bump patch (domyślnie)
make tag PART=minor     # albo minor / major
```

Podbija `cockpit/pyproject.toml` + zsynchronizowane kopie, przenosi
zawartość `## [Unreleased]` w `CHANGELOG.md` do nowej sekcji
`## [X.Y.Z] - DATA`, commituje (`chore: checkpoint vX.Y.Z`), taguje jako
`checkpoint/vX.Y.Z` i pushuje oba — commit i tag, nic nie zostaje
lokalnie. Wciąż jest niewidoczny dla `orcan update`/`downgrade` i
`release.yml` (patrz Model wyżej), więc push nie może odpalić release'u
ani publikacji docs; job `checks` w CI i tak testuje commit (odpala się
na każdy push do `main`, niezależnie od tagów).

## Release — `make release`

Rzadki, świadomy, publiczny stop (orientacyjnie raz na kwartał, ale to
decyzja, nie automat).

```bash
make release             # etykieta CalVer = bieżący kwartał (YY.Q)
make release Q=26.3      # etykieta jawnie podana
```

Kroki, które to wykonuje:

1. Jeśli `[Unreleased]` wciąż coś zawiera, najpierw robi automatyczny checkpoint (żeby nic nie zginęło).
2. Dokłada separator `## YY.Q — DATA` w `CHANGELOG.md`, tuż nad każdą sekcją `[X.Y.Z]` zebraną od poprzedniego separatora.
3. Commituje (`release: YY.Q (vX.Y.Z)`).
4. Upewnia się, że istnieje realny tag `vX.Y.Z` (tworzy go, jeśli `make tag` jeszcze tego nie zrobił) — push tego tagu odpala `.github/workflows/release.yml`.
5. Taguje ten sam commit jako `26.3` (goły CalVer, odmawia jeśli ta etykieta była już użyta) i też go pushuje.

CI następnie waliduje, publikuje docs `X.Y.Z` (+ alias `YY.Q`, odczytany
z separatora w `CHANGELOG.md` — nigdy nie rusza `latest`) i tworzy
GitHub Release z tytułem `Orcan YY.Q (vX.Y.Z)`.

## Lokalne tagi po buildzie

`orcan build` taguje też lokalnie `orcan:VERSION`. To tylko na Twojej maszynie.

## Zobacz też

- [Changelog](../changelog.md)
- [Wdrożenie](../deployment.md)
- [Przegląd rozwoju](overview.md)
- [Wydania na GitHubie](https://github.com/aKyther/orcan/releases)
