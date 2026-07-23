---
description: Opisz workspace'y i projekty w orcan.config.json — najpierw historia kontekstu, potem zastosowanie.
---

# Konfiguracja

## Dlaczego plik konfiguracji

Twoja praca multi-repo to **historia**: które projekty tworzą który workspace. `orcan.config.json` to ta historia w danych. Make nie wymyśla układu; stosuje to, co opiszesz.

Jeśli Project / Workspace / Context są niejasne, najpierw przeczytaj [Idee podstawowe](../ideas/core-ideas.md).

## Źródło prawdy

Konfiguracja hosta to **tylko JSON**:

```text
orcan.config.json
```

Szablon: `orcan.config.example.json`.

Po edycji zawsze uruchom:

```bash
make env
```

!!! note
    `make terminal*` **nie** uruchamia `make env`. Najpierw zastosuj konfigurację, potem odtwórz kontener.

Potem odtwórz kontener, jeśli już działa:

```bash
make down && make terminal-docker
```

## Kształt (przykład)

```json
{
  "workspaces": [
    {
      "name": "myapp",
      "projects": [
        {
          "name": "backend",
          "path": "/absolute/path/to/myapp/backend"
        },
        {
          "name": "frontend",
          "path": "/absolute/path/to/myapp/frontend"
        }
      ]
    }
  ],
  "tmux": {
    "initial_windows": 3,
    "window_prefix": "tab"
  },
  "ttyd": {
    "port": 7681,
    "host_port": 7681,
    "font_size": 22,
    "theme": "dark"
  },
  "resources": {
    "cpus": 8,
    "memory": "16g",
    "shm_size": "2g",
    "tmpfs_size": "2g"
  }
}
```

### Uwagi do pól

| Pole | Znaczenie |
| --- | --- |
| `workspaces[].name` | Nazwa sesji tmux oraz folder pod `/home/developer/workspaces/` |
| `projects[].name` | Nazwa symlinku wewnątrz workspace'a |
| `projects[].path` | Bezwzględna ścieżka hosta (ta sama w kontenerze — path parity) |
| `tmux.*` | Okna tworzone przy starcie sesji |
| `ttyd.*` | Port i wygląd terminala w przeglądarce |
| `resources.*` | Limity CPU / pamięci kontenera |

## Sposoby edycji

| Polecenie | Kiedy użyć |
| --- | --- |
| `make config-wizard` | Interaktywne tworzenie/edycja |
| `make config-scaffold PROJECT_DIR=…` | Dodanie jednego projektu bez interakcji |
| `make setup PROJECT_DIR=…` | Pierwszy uruchomienie |
| Ręczna edycja JSON | Znasz schemat |

Pokaż bieżący układ:

```bash
make config-show
make path-check
```

## Co zapisuje `make env`

| Wynik | Rola |
| --- | --- |
| `.env` | Zmienne Compose i Make |
| `.orcan/runtime-config.json` | Montowany do kontenera jako `/etc/orcan/config.json` |
| `.orcan/compose-projects.generated.yml` | Dodatkowe bind mounty |
| `.orcan/workspaces/<name>/` | Meta workspace'a po stronie hosta |
| Drzewo `$ORCAN_DATA` | Domyślnie `~/.config/orcan` (home Cursor/Claude, cache) |

Nie commituj `.env` ani `.orcan/` (są w gitignore).

## Seed plików projektu (opcjonalnie)

Orcan **nie** przepisuje każdego zamontowanego repo przy starcie. Aby raz zaseedować ignores/szablony:

```bash
make init-project-all
# or dry-run:
make init-project-all-dry-run
```

Pełne reguły pól i odrzucane klucze: [Referencja konfiguracji](../reference/configuration.md).

## Zobacz też

- [Referencja konfiguracji](../reference/configuration.md)
- [Zmienne środowiskowe](../reference/environment.md)
- [Workspaces](../concepts/workspaces.md)
- [Szybki start](quickstart.md)
