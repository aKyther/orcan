# Makefile (maintainerzy)

Użytkownicy końcowi używają **CLI `orcan`** — zobacz [Referencja CLI](cli.md). Cykl życia obrazu na hoście:

| Potrzeba | Komenda |
| --- | --- |
| Zbuduj lokalny obraz | `orcan build --agent codex` (albo `--all-agents`; **nigdy nie publikuje**) |
| Wymuś lokalny rebuild | `orcan build --agent codex --force` lub `--no-cache` |
| Tylko pull z rejestru | `orcan pull` |
| Push do rejestru | `orcan publish` (**ręcznie**, maintainerzy) |

Repozytorium ma Makefile tylko dla **maintainerów** w checkoutcie gita:

| Cel | Rola |
| --- | --- |
| `make validate` | Layout + składnia skryptów |
| `make test-host` | Testy jednostkowe hosta |
| `make test` / `make test-path-parity` | Testy kontenera (wymaga Dockera) |
| `make dev-test` | Lifecycle izolowanego UX developerskiego (Docker + `orcan:dev-ux`) |
| `make docs` / `docs-serve` / `docs-check` | MkDocs |
| `make docs-llms` | Regeneruj `docs/llms.txt` (też przed docs / docs-check) |
| `make docs-mike-latest` / `docs-mike-release` | Wersjonowany deploy docs |
| `make tag` | Checkpoint: bump + cięcie CHANGELOG + commit + tag, wszystko pushowane (patrz [Proces wydania](../development/release.md)) |
| `make release` | Właściwy, świadomy release: CalVer + tag + push |
| `make registry-*` | Niskopoziomowe helpery rejestru (preferuj `orcan publish` / `orcan pull`) |

Przestarzałe cele użytkownika (`setup`, `env`, `terminal-docker`, `rebuild`, …) przekazują do `./bin/orcan` z notką deprecacji. **Nie dokumentuj ich użytkownikom końcowym** — używaj bezpośrednio `orcan`.

## Środowisko developerskie (`make dev-*`)

Izolowany UX przeglądarkowy do testów cockpit / ttyd / launcher. To **nie** jest publiczny interfejs `orcan` — własny obraz, port i stan pod `.orcan-dev-ux/`.

| Cel | Rola |
| --- | --- |
| `make dev-start` | Start; build obrazu tylko gdy brakuje |
| `make dev-restart` | Odśwież cockpit z checkoutu i odtwórz kontener |
| `make dev-status` | Health + URL lokalny/LAN |
| `make dev-doctor` | Tożsamość izolacji, health, HTTP, cockpit z checkoutu |
| `make dev-smoke` | Smoke Textual + prawdziwy osadzony tmux PTY |
| `make dev-visual` | Regresja screenshotów w Chromium (wymaga healthy preview) |
| `make dev-visual-update` | Zastąp wzorce screenshotów po przeglądzie |
| `make dev-a11y` | Tab/focus, overflow, axe, tiny viewport `480x320` |
| `make dev-shell` | Wejście do izolowanego kontenera preview |
| `make dev-enter` | Wejście do izolowanego launchera developerskiego |
| `make dev-logs` | Logi kontenera |
| `make dev-stop` | Stop; zachowaj obraz/cache |
| `make dev-reset` | Stop i usuń domyślny stan `.orcan-dev-ux/` |
| `make dev-checklist` | Cele Make przed merge’em + ręczny flow w przeglądarce |
| `make dev-test` | Osobny stack o unikalnej nazwie; assert że `orcan-1` bez zmian |

Skrypty pod spodem (to samo zachowanie): `./scripts/dev/orcan-preview …` oraz `./scripts/dev/terminal-ui-preview` (szybki tmux bez Dockera).

Domyślnie: obraz `orcan:dev-ux`, port hosta `17681`, workspace `dev-ux`, scenariusz `busy`. Flagi, scenariusze i izolacja: [Testy — preview maintainerów](../development/testing.md).

## Opcjonalny prywatny rejestr

CI **nie** publikuje obrazów kontenerów. Maintainerzy mogą pchać ręcznie:

```bash
orcan build --all-agents --force # upewnij się, że istnieje obraz do publikacji
orcan publish                # albo: make registry-login && ./scripts/repository/registry.sh publish
```

Skonfiguruj `IMAGE_REGISTRY`, `IMAGE_REPOSITORY` i `IMAGE_TAG` w `.env` (przez `orcan sync`). Zobacz [Zmienne środowiskowe](environment.md).
