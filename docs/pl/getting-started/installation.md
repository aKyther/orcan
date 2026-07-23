---
description: Wymagania hosta dla Orcana — izolacja Dockera to wybór produktowy, nie przypadek.
---

# Instalacja

## Dlaczego te wymagania

Orcan izoluje toolchainy agentów w Dockerze, żeby host został cienki. Ten wybór wymaga Docker Compose, Make (cienkie UI hosta), Gita (klon tego repo i Twoich projektów) oraz Pythona 3 (skrypty konfiguracji na hoście).

Jeśli nie chcesz Dockera, Orcan nie jest właściwym narzędziem — zobacz [Dlaczego Orcan?](../why-orcan.md).

## Zanim zaczniesz

Orcan działa na maszynie z Dockerem. Większość osób używa Linuksa lub WSL2.

## Wymagania

| Narzędzie | Uwagi |
| --- | --- |
| Docker Engine | Z Compose v2 (`docker compose`) |
| Make | GNU Make |
| Git | Do sklonowania tego repozytorium |
| Python 3 | Do skryptów konfiguracji na hoście (`make env`, wizard) |

Opcjonalnie:

| Narzędzie | Uwagi |
| --- | --- |
| `gh` | Tylko do helperów `make docs-publish` / `make release` |
| Tailscale | Opcjonalny prywatny dostęp do terminala w przeglądarce |

Sprawdź wersje:

```bash
docker version
docker compose version
make --version
python3 --version
```

## Pobierz kod

```bash
git clone https://github.com/aKyther/orcan.git
cd orcan
```

## Pierwsza konfiguracja

Opisz workspace'y w `orcan.config.json`, potem **zmaterializuj** pliki, które czyta Compose:

```bash
make setup PROJECT_DIR=/absolute/path/to/your/repo
```

`make setup` tworzy konfigurację, gdy jej brakuje, i uruchamia **`make env`** (zapisuje `.env` + `.orcan/*`). Po każdej kolejnej edycji konfiguracji ponów `make env` — `make build` / `make terminal*` tylko je konsumują; nie regenerują ich.

Albo użyj wizarda:

```bash
make config-wizard
make env
```

## Zbuduj obraz

=== "Pełny (domyślny)"

    ```bash
    make build
    ```

    Tag: `orcan:latest` (także `orcan:full`) — Claude Code + Cursor CLI.

=== "Tylko Claude"

    ```bash
    make build-claude
    IMAGE_LOCAL=orcan:claude make terminal-docker
    ```

    Tag: `orcan:claude` — tylko Claude.

## Oczekiwany wynik

- Istnieją `.env` oraz `.orcan/`
- Lokalny obraz `orcan:latest` (lub `orcan:claude`) istnieje
- `make path-check` wypisuje ścieżki workspace'ów

## Odinstalowanie

Zobacz [Workflowy — odinstalowanie](../guides/workflows.md#odinstalowanie) lub [FAQ](../faq.md#uninstall).

## Częste problemy

| Problem | Co spróbować |
| --- | --- |
| Docker permission denied | Dodaj użytkownika do grupy `docker` albo użyj rootless Docker |
| `make env` pada na `PROJECT_DIR` | Użyj ścieżki **bezwzględnej**; nie używaj `/`, `/home` ani `/etc` jako projektu |
| Wolny pierwszy build | Normalne — obraz instaluje toolchainy i CLI |

Dalej: [Szybki start](quickstart.md).

## Zobacz też

- [Szybki start](quickstart.md)
- [Konfiguracja](configuration.md)
- [Wdrożenie](../deployment.md)
- [Bezpieczeństwo](../reference/security.md)
