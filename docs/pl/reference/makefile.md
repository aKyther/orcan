# Makefile (maintainerzy)

Użytkownicy końcowi używają **CLI `orcan`** — zobacz [Referencja CLI](cli.md). Cykl życia obrazu na hoście:

| Potrzeba | Komenda |
| --- | --- |
| Pull albo build | `orcan build` (pull `VERSION`, lokalny build przy braku — **nigdy nie publikuje**) |
| Wymuś lokalny rebuild | `orcan build --force` lub `--no-cache` |
| Tylko pull z rejestru | `orcan pull` |
| Push do rejestru | `orcan publish` (**ręcznie**, maintainerzy) |

Repozytorium ma Makefile tylko dla **maintainerów** w checkoutcie gita:

| Cel | Rola |
| --- | --- |
| `make validate` | Layout + składnia skryptów |
| `make test-host` | Testy jednostkowe hosta |
| `make test` / `make test-path-parity` | Testy kontenera (wymaga Dockera) |
| `make docs` / `docs-serve` / `docs-check` | MkDocs |
| `make docs-llms` | Regeneruj `docs/llms.txt` (też przed docs / docs-check) |
| `make docs-mike-dev` / `docs-mike-release` | Wersjonowany deploy docs |
| `make bump-*` / `release` | Wersja + GitHub Release |
| `make registry-*` | Niskopoziomowe helpery rejestru (preferuj `orcan publish` / `orcan pull`) |

Przestarzałe cele użytkownika (`setup`, `env`, `terminal-docker`, `rebuild`, …) przekazują do `./bin/orcan` z notką deprecacji. **Nie dokumentuj ich użytkownikom końcowym** — używaj bezpośrednio `orcan`.

## Opcjonalny prywatny rejestr

CI **nie** publikuje obrazów kontenerów. Maintainerzy mogą pchać ręcznie:

```bash
orcan build --force          # upewnij się, że lokalny obraz istnieje
orcan publish                # albo: make registry-login && ./scripts/repository/registry.sh publish
```

Skonfiguruj `IMAGE_REGISTRY`, `IMAGE_REPOSITORY` i `IMAGE_TAG` w `.env` (przez `orcan sync`). Zobacz [Zmienne środowiskowe](environment.md).
