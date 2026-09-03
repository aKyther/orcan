---
description: Wymagania hosta dla Orcana — izolacja Dockera to wybór produktowy, nie przypadek.
---

# Instalacja

## Dlaczego te wymagania

Orcan izoluje toolchainy agentów w Dockerze, żeby host został cienki. Ten wybór wymaga Docker Compose, Gita (klon instalacji i Twoich projektów), Pythona 3 (skrypty konfiguracji na hoście) oraz Bash (CLI `orcan`).

Jeśli nie chcesz Dockera, Orcan nie jest właściwym narzędziem — zobacz [Dlaczego Orcan?](../why-orcan.md).

## Zanim zaczniesz

Orcan działa na maszynie z Dockerem. Większość osób używa Linuksa lub WSL2.

## Wymagania

| Narzędzie | Uwagi |
| --- | --- |
| Docker Engine | Z Compose v2 (`docker compose`) |
| Git | Do klonowania instalacji i projektów |
| Python 3 | Skrypty konfiguracji na hoście — `orcan sync`, `init` (w tym kreator), `context`. Tylko stdlib; bez pip. |
| Bash | Launcher CLI |

Opcjonalnie:

| Narzędzie | Uwagi |
| --- | --- |
| `gh` | Tylko do helperów `make docs-publish` / `make release` |
| Tailscale | Opcjonalny prywatny dostęp do terminala w przeglądarce |

Sprawdź wersje:

```bash
docker version
docker compose version
python3 --version
bash --version
```

## Zainstaluj CLI

```bash
curl -fsSL https://raw.githubusercontent.com/aKyther/orcan/main/install.sh | bash
```

`install.sh` kładzie launcher w `~/.local/bin` i dopisuje ten katalog do shell rc (idempotentnie; pomiń przez `ORCAN_SKIP_PATH=1`). Instalacja przez `curl | bash` **nie może** zmienić `PATH` w shellu rodzica, więc zanim uruchomisz `orcan doctor`:

1. Upewnij się, że `~/.local/bin` jest na `PATH` (`echo "$PATH"` albo `command -v orcan`).
2. Jeśli installer dopisał linię do rc, ale ta sesja jej jeszcze nie ma — przeładuj shell, np. `exec bash -l`, `exec zsh -l`, albo otwórz nowy terminal. Jednorazowo: `export PATH="$HOME/.local/bin:$PATH"`.
3. Jeśli rc nie zostało zaktualizowane, dodaj export ręcznie, przeładuj sesję i dopiero potem idź dalej.

```bash
orcan doctor
```

Z checkoutu gita tego repozytorium możesz też uruchomić `./bin/orcan` bez instalacji.

## Pierwsza konfiguracja

Opisz workspace'y w `~/.config/orcan/orcan.config.json`, potem **zmaterializuj** pliki, które czyta Compose:

```bash
orcan init /absolute/path/to/your/repo
```

`orcan init` tworzy konfigurację, gdy jej brakuje, i uruchamia **`orcan sync`** (zapisuje `.env` + `mounts/*` pod `ORCAN_HOME`). Po każdej kolejnej edycji konfiguracji ponów `orcan sync` — `orcan build` / `orcan up` tylko je konsumują; nie regenerują ich.

Albo użyj wizarda:

```bash
orcan init
orcan sync
```

## Budowa obrazu

Wybierz klientów CLI pieczonych w zwykłym obrazie Orcan. Wybór jest jawny;
nie ma tagów obrazów per agent.

```bash
orcan build --agent codex
orcan build --agent gemini --agent copilot
orcan build --all-agents
```

Każde polecenie aktualizuje `orcan:latest` i `orcan:<VERSION>`. `orcan status`
oraz `orcan doctor` pokazują manifest obrazu. Gemini i Copilot trzymają trwałe
loginy/sesje w `ORCAN_DATA/gemini` oraz `ORCAN_DATA/copilot`.

## Oczekiwany wynik

- Config i `.env` istnieją pod `~/.config/orcan/`
- Lokalny obraz `orcan:latest` istnieje
- `orcan context show` wypisuje ścieżki workspace'ów

Tożsamość autora Gita wypełnia `orcan sync`. Żeby podpiąć hostowe klucze SSH do push/pull, użyj `orcan up --with-git` (zobacz [Szybki start](quickstart.md#git-w-kontenerze)).

## Odinstalowanie

```bash
orcan uninstall              # usuń launcher + klon instalacji
orcan uninstall --purge-data # usuń też config/loginy/cache; projekty zostają
orcan uninstall --purge-images # usuń też lokalne tagi obrazów orcan:*
```

Zobacz [Workflowy — uninstall](../guides/workflows.md#uninstall) lub [FAQ](../faq.md#uninstall).

## Typowe problemy

| Problem | Co spróbować |
| --- | --- |
| Docker permission denied | Dodaj użytkownika do grupy `docker` albo użyj rootless Docker |
| `orcan sync` pada na `PROJECT_DIR` | Użyj ścieżki **bezwzględnej**; nie używaj `/`, `/home` ani `/etc` jako projektu |
| Wolny pierwszy build | Normalne — obraz instaluje toolchainy i CLI |
| `orcan: command not found` | Upewnij się, że `~/.local/bin` jest na `PATH`, potem przeładuj shell (`exec bash -l` / nowy terminal) albo `export PATH="$HOME/.local/bin:$PATH"`; ponów `install.sh`, jeśli brakuje linii w rc |

Dalej: [Szybki start](quickstart.md) · [Referencja CLI](../reference/cli.md).
