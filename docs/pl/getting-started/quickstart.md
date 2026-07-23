---
description: Sklonuj Orcana, zbuduj obraz i otwórz terminal — gdy już rozumiesz ideę produktu.
---

# Szybki start

Powinieneś już wiedzieć, po co Orcan istnieje ([Dlaczego Orcan?](../why-orcan.md)) i czym jest **workspace** ([Idee podstawowe](../ideas/core-ideas.md)). Ta strona tylko uruchamia.

## Zanim zaczniesz

- Docker działa  
- Bezwzględna ścieżka do co najmniej jednego repo git do zamontowania  

## Kroki (host)

```bash
cd /absolute/path/to/orcan
make setup PROJECT_DIR=/absolute/path/to/your/repo
make build
make terminal-docker
```

Otwórz URL wypisany w terminalu (domyślnie `http://localhost:7681`).

## W przeglądarce

1. Wybierz **workspace** z launchera (lub Enter dla domyślnego).  
2. Trafiasz do **tmux** z **zsh**.  
3. Sprawdź narzędzia:

```bash
agent --version
claude --version
pwd
```

## Oczekiwany wynik

- Ciemny terminal w przeglądarce  
- Launcher listuje workspace'y  
- `agent` i/lub `claude` odpowiadają na `--version`  

## Częste problemy

| Problem | Rozwiązanie |
| --- | --- |
| Port 7681 zajęty | Ustaw `ttyd.host_port` w konfiguracji, potem `make env` |
| Pusty launcher | Sprawdź workspace'y w `orcan.config.json`, potem `make env` |
| Błędy socketa przy Docker-in-Docker | Użyj `make terminal-docker` (nie `make terminal`) |

!!! tip
    Po edycji `orcan.config.json` uruchom `make env` przed odtworzeniem kontenera. `make terminal*` **nie** odświeża konfiguracji. Zobacz [Workflowy](../guides/workflows.md).

Warianty obrazu: [Instalacja](installation.md) i [FAQ](../faq.md).

## Zobacz też

- [Instalacja](installation.md)  
- [Konfiguracja](configuration.md)  
- [Model mentalny](../ideas/mental-model.md)
