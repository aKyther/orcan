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
| `make test-host` | Testy jednostkowe config I/O, `apply-config`, wersja / release check |
| `make docs-check` | Ścisły MkDocs (EN+PL) + kontrola nazwy produktu |

## Testy smoke (pełny obraz — lokalnie)

```bash
make test
```

Uruchamia `tests/smoke/test-container.sh` po `orcan build`. Oczekuje **pełnego** obrazu (obecny `agent`). Nie działa w CI (build obrazu jest za ciężki).

## Izolowany podgląd UX

Uruchom pełny terminal przeglądarkowy i launcher z bieżącego checkoutu bez
podmieniania zainstalowanego obrazu Orcana ani dotykania jego konfiguracji,
danych, kontenera, portu czy serwera tmux:

```bash
./scripts/dev/orcan-preview up
# otwórz http://127.0.0.1:17681
./scripts/dev/orcan-preview down
```

Preview używa osobnych: `ORCAN_HOME`, `ORCAN_DATA`, projektu Compose,
kontenera (`orcan-ux-preview`), obrazu (`orcan:ux-preview`) i portu ttyd.
Dodaje też dwie tymczasowe Context Assertions, dzięki czemu panel boczny
cockpitu można przetestować od razu. Dostępne są również polecenia `status`,
`url`, `logs`, `shell` i `rebuild`; zobacz
`./scripts/dev/orcan-preview --help`.

Preview publikuje port na `0.0.0.0`, więc można go też otworzyć przez adres IP
hosta w LAN. Nie uruchamiaj go w niezaufanej sieci bez uwierzytelniania ttyd.

Dla zmian paska statusu i layoutu tmuxa użyj szybszego preview z checkoutu:

```bash
./scripts/dev/terminal-ui-preview
```

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
    CI **nie** buduje obrazów kontenera i **nie** uruchamia `make test` ani `make test-path-parity`.
    Zielony PR oznacza validate + testy hosta + docs — nie zweryfikowany smoke obrazu. Uruchamiaj je lokalnie, gdy zmienia się zachowanie Dockera.

URL docs: https://akyther.github.io/orcan/latest/ — zobacz [Wdrożenie](../deployment.md).

Wyszukiwanie PL używa angielskiego analizatora lunr (brak polskiego stemmera).

## Zobacz też

- [Przegląd rozwoju](overview.md)
- [Proces wydania](release.md)
- [Referencja Makefile](../reference/makefile.md)
- [Path parity](../concepts/path-parity.md)
