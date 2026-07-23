# Referencja Makefile

Uruchamiaj z katalogu głównego repozytorium Orcana na **hoście**.

!!! note
    Trzymaj tę stronę zsynchronizowaną z `make help`. Dokumentuj każdy target z adnotacją `##`.

## Konfiguracja

| Cel | Przeznaczenie |
| --- | --- |
| `make setup` | Pierwszy start: scaffold konfiguracji w razie potrzeby → `env` → pokaż układ |
| `make config-wizard` | Interaktywna edycja `orcan.config.json` |
| `make config-scaffold` | Dodaj projekt z `PROJECT_DIR` |
| `make config-init` | Skopiuj przykładowy plik konfiguracji |
| `make config-show` | Wypisz workspace'y |
| `make env` | Zastosuj konfigurację → `.env` + `.orcan/*` |
| `make require-generated` | Fail, gdy brak `.env` / wygenerowanych plików (bez zapisów) |
| `make require-env` | Fail, gdy brak `.env` (build obrazu) |

## Obrazy

| Cel | Przeznaczenie |
| --- | --- |
| `make build` | Pełny obraz → `orcan:latest` (Claude + Cursor) |
| `make build-claude` | Tylko Claude → `orcan:claude` |
| `make rebuild` / `make rebuild-claude` | Rebuild bez cache |

## Uruchomienie

| Cel | Przeznaczenie |
| --- | --- |
| `make terminal` | Terminal w przeglądarce **bez** socketa Dockera |
| `make terminal-docker` | Terminal w przeglądarce **z** socketem Dockera |
| `make terminal-url` | Wypisz URL |
| `make down` | Zatrzymaj kontenery |
| `make logs` | Śledź logi |
| `make path-check` | Pokaż podsumowanie path parity |
| `make config` | Wypisz rozwiązaną konfigurację Compose |

`make terminal*` **nie** uruchamia `make env`.

## Seedy projektów

| Cel | Przeznaczenie |
| --- | --- |
| `make init-project` | Seed `PROJECT_DIR` (tylko gdy brakuje) |
| `make init-project-dry-run` | Podgląd seedów dla `PROJECT_DIR` |
| `make init-project-all` | Seed każdej skonfigurowanej ścieżki projektu |
| `make init-project-all-dry-run` | Podgląd seedów dla każdej ścieżki projektu |

## Docs

| Cel | Przeznaczenie |
| --- | --- |
| `make docs` | Build MkDocs → `./site` (strict) |
| `make docs-serve` | Lokalny serwer docs |
| `make docs-check` | Strict build + sprawdzenie nazwy produktu |
| `make docs-mike-dev` | Deploy aliasu mike `dev` |
| `make docs-mike-release` | Deploy `VERSION` + alias `latest` przez mike |
| `make docs-publish` | Wyzwól CI (main → docs `dev`) |
| `make docs-deploy` | Alias dla `docs-publish` |

## Jakość

| Cel | Przeznaczenie |
| --- | --- |
| `make validate` | Układ, składnia skryptów, konfiguracja Compose |
| `make test-host` | Testy hosta (bez obrazu Dockera) |
| `make test` | Testy smoke (buduje pełny obraz; **nie** w CI) |
| `make test-path-parity` | Test integracyjny path parity (**nie** w CI) |

## Wydanie

| Cel | Przeznaczenie |
| --- | --- |
| `make version` | Pokaż `VERSION` i lokalne nazwy tagów obrazu |
| `make bump-patch` / `bump-minor` / `bump-major` | Podbij SemVer |
| `make release-tag` | Utwórz annotated tag git `vX.Y.Z` (czyste drzewo) |
| `make release-push` | Wypchnij tag wersji na origin |
| `make release` | Tag + push → GitHub Release (**bez** publikacji obrazu) |

## Czyszczenie

| Cel | Przeznaczenie |
| --- | --- |
| `make clean` | Zatrzymaj kontenery; zachowaj `$ORCAN_DATA` |
| `make clean-data` | **Destrukcyjne** usunięcie `$ORCAN_DATA` (potwierdź `yes`) |
| `make clean-volumes` | Alias dla `clean-data` |

## Opcjonalny prywatny rejestr

| Cel | Przeznaczenie |
| --- | --- |
| `make registry-show` | Pokaż lokalne/zdalne nazwy obrazów |
| `make registry-login` | Zaloguj do rejestru kontenerów |
| `make publish` / `make pull` | Ręczny push/pull obrazu (nieużywane przez CI) |

## Przemianowane cele (migracja)

| Stare | Nowe |
| --- | --- |
| `make shell` | `make terminal` |
| `make shell-docker` | `make terminal-docker` |

## Zobacz też

- [Typowe workflowy](../guides/workflows.md)
- [Zmienne środowiskowe](environment.md)
- [Docker](docker.md)
- [Testy](../development/testing.md)
