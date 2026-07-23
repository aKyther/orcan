# Instalacja

## Co to robi

Wypisuje, czego potrzebujesz na **hoście**, zanim uruchomisz Orcana.

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

Katalog clone'a może nadal nazywać się `cind`, jeśli forknąłeś starszą ścieżkę. To w porządku. Ścieżki produktu używają `orcan` (konfiguracja, `$HOME/.config/orcan`, nazwa obrazu `orcan`).

## Pierwsza konfiguracja

```bash
make setup PROJECT_DIR=/absolute/path/to/your/repo
```

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
