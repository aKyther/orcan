---
description: Sklonuj Orcana, zbuduj obraz i otwórz terminal w przeglądarce w kilku poleceniach.
---

# Szybki start

## Zanim zaczniesz

- Docker działa
- Bezwzględna ścieżka do co najmniej jednego repozytorium git do zamontowania

## Kroki (host)

```bash
cd /absolute/path/to/orcan
make setup PROJECT_DIR=/absolute/path/to/your/repo
make build
make terminal-docker
```

Otwórz URL wypisany w terminalu (domyślnie `http://localhost:7681`).

## W przeglądarce

1. Wybierz **workspace** z launchera (lub naciśnij Enter dla domyślnego).
2. Trafiasz do **tmux** z **zsh**.
3. Sprawdź narzędzia:

```bash
agent --version
claude --version
pwd
```

## Oczekiwany wynik

- W przeglądarce widać ciemny terminal
- Launcher listuje Twoje workspace'y
- `agent` i/lub `claude` odpowiadają na `--version`

## Częste problemy

| Problem | Rozwiązanie |
| --- | --- |
| Port 7681 zajęty | Ustaw `ttyd.host_port` w konfiguracji, potem `make env` |
| Pusty launcher | Sprawdź workspace'y w `orcan.config.json`, potem `make env` |
| Błędy socketa przy Docker-in-Docker | Użyj `make terminal-docker` (nie `make terminal`) |

!!! tip
    Po edycji `orcan.config.json` uruchom `make env` przed odtworzeniem kontenera. `make terminal*` **nie** odświeża konfiguracji. Zobacz [Workflowy](../guides/workflows.md).

Warianty obrazu (`orcan:latest` vs `orcan:claude`): [Instalacja](installation.md) i [FAQ](../faq.md).

## Zobacz też

- [Instalacja](installation.md)
- [Konfiguracja](configuration.md)
- [Workflowy](../guides/workflows.md)
