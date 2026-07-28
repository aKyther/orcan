# Testy

## Kontrole hosta (szybkie — CI)

```bash
make validate
make test-host
make docs-check
```

| Target | Co robi |
| --- | --- |
| `make validate` | Wymagane pliki, składnia shell/Python, VERSION, nazwa produktu, Compose `config` gdy Docker działa |
| `make test-host` | Testy jednostkowe config I/O, `apply-config`, VERSION / release check |
| `make docs-check` | Ścisły MkDocs (EN+PL) + kontrola nazwy produktu |

## Testy smoke (pełny obraz — lokalnie)

```bash
make test
```

Uruchamia `tests/smoke/test-container.sh` po `orcan build`. Oczekuje **pełnego** obrazu (obecny `agent`). Nie działa w CI (build obrazu jest za ciężki).

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
