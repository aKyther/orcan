---
description: Zainstaluj CLI orcan, zsynchronizuj config, zbuduj obraz, otwórz terminal.
---

# Szybki start

Powinieneś już wiedzieć, po co Orcan istnieje ([Dlaczego Orcan?](../why-orcan.md)) i czym jest **workspace** ([Idee podstawowe](../ideas/core-ideas.md)). Ta strona tylko uruchamia.

## Zanim zaczniesz

- Docker działa  
- Bezwzględna ścieżka do co najmniej jednego repo git do zamontowania  

## Zainstaluj CLI

```bash
curl -fsSL https://raw.githubusercontent.com/aKyther/orcan/main/install.sh | bash
```

Upewnij się, że `~/.local/bin` jest na `PATH`, potem:

```bash
orcan doctor
```

## Kroki

Konfiguracja to JSON w `~/.config/orcan/home/`. Docker widzi tylko to, co zapisze **`orcan sync`** (`.env` + `.orcan/*`).

```bash
orcan init /absolute/path/to/your/repo   # scaffold + sync
orcan sync                               # odśwież po późniejszych edycjach
orcan build
orcan up
```

!!! note
    `orcan init` już raz uruchamia `sync`. Trzymaj `orcan sync` w nawyku: **każda** edycja konfiguracji wymaga go przed `orcan build` / `orcan up`. Te komendy **nie** regenerują plików runtime.

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

- Przeglądarka pokazuje ciemny terminal  
- Launcher listuje Twoje workspace'y  
- `agent` i/lub `claude` odpowiadają na `--version`  

## Typowe problemy

| Problem | Fix |
| --- | --- |
| Port 7681 zajęty | Ustaw `ttyd.host_port` w configu, potem `orcan sync` |
| Pusty launcher | Sprawdź workspace'y w configu, potem `orcan sync` |
| Błędy socketu Docker-in-Docker | Użyj `orcan up --with-docker` |

!!! tip
    Po edycji `orcan.config.json` uruchom `orcan sync` przed odtworzeniem kontenera. `orcan up` **nie** odświeża konfiguracji. Zobacz [Workflowy](../guides/workflows.md).

Warianty obrazu: [Instalacja](installation.md) i [FAQ](../faq.md).

## Zobacz też

- [Instalacja](installation.md)  
- [Konfiguracja](configuration.md)  
- [Referencja CLI](../reference/cli.md)  
- [Model mentalny](../ideas/mental-model.md)
