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

```bash
orcan doctor
```

(`install.sh` dopisuje `~/.local/bin` do rc shella; w *bieżącym* terminalu może być potrzebne `export PATH="$HOME/.local/bin:$PATH"` albo nowa sesja.)

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

## Git w kontenerze

`orcan sync` kopiuje tożsamość z hostowego `git config --global` (`user.name` / `user.email`), żeby commity w środku miały tego samego autora co na hoście.

Zwykłe `orcan up` **nie** montuje kluczy SSH. Do push/pull po SSH z kontenera:

```bash
orcan up --with-git
# opcjonalnie DinD jednocześnie:
orcan up --with-docker --with-git
```

Montuje hostowy `~/.ssh` tylko do odczytu (oraz agenta SSH, gdy `SSH_AUTH_SOCK` jest ustawiony). Obie flagi są opcjonalne i wypisują ostrzeżenie bezpieczeństwa — agenci w kontenerze mogą użyć zamontowanego socketa/kluczy. Szczegóły: [Workflowy](../guides/workflows.md), [Bezpieczeństwo](../reference/security.md).

`orcan context wizard` — dodaj workspace i ścieżki projektów. Domyślnie: montuj folder jak leży. Opcjonalnie (zaawansowane) utwórz lub wybierz git worktree. Zobacz [Workspace'y](../concepts/workspaces.md#git-worktree).

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
| `git push` pada (SSH) w kontenerze | Użyj `orcan up --with-git` |

!!! tip
    Po edycji `orcan.config.json` uruchom `orcan sync` przed odtworzeniem kontenera. `orcan up` **nie** odświeża konfiguracji. Zobacz [Workflowy](../guides/workflows.md).

Warianty obrazu: [Instalacja](installation.md) i [FAQ](../faq.md).

## Zobacz też

- [Instalacja](installation.md)  
- [Konfiguracja](configuration.md)  
- [Referencja CLI](../reference/cli.md)  
- [Model mentalny](../ideas/mental-model.md)
