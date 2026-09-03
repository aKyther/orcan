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
orcan sync
```

!!! note
    `orcan up` **nie** uruchamia `orcan sync`. Najpierw zastosuj konfigurację, potem odtwórz kontener.

Potem odtwórz kontener, jeśli już działa:

```bash
orcan down && orcan up
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
    "font_size": 14,
    "theme": "dark"
  },
  "resources": {
    "cpus": 2,
    "memory": "4g",
    "shm_size": "512m",
    "tmpfs_size": "512m"
  }
}
```

Domyślne limity są celowo lekkie (typowy laptop). Podnieś je, gdy maszyna ma zapas — poniżej.

### Uwagi do pól

| Pole | Znaczenie |
| --- | --- |
| `workspaces[].name` | Nazwa sesji tmux oraz folder pod `/home/developer/workspaces/` |
| `projects[].name` | Nazwa symlinku wewnątrz workspace'a |
| `projects[].path` | Bezwzględna ścieżka hosta (ta sama w kontenerze — path parity) |
| `tmux.*` | Okna tworzone przy starcie sesji |
| `ttyd.*` | Port, wygląd (`theme`: `dark`/`navy`, `mocha` albo surowy JSON) i `ping_interval` (keepalive WebSocket) terminala w przeglądarce |
| `resources.*` | Limity CPU / pamięci / shm / tmpfs kontenera |

### Podnoszenie zasobów

Edytuj `resources` w `orcan.config.json` (np. `cpus: 8`, `memory: "16g"`), potem:

```bash
orcan sync
orcan down && orcan up
```

Jeśli `.env` ma już `CPUS` / `MEMORY`, `orcan sync` ich nie nadpisze. Zmień je też w `.env`, albo usuń klucze, żeby config wygrał przy następnym `orcan sync`.

## Sposoby edycji

| Polecenie | Kiedy użyć |
| --- | --- |
| `orcan init` | Interaktywne tworzenie/edycja |
| `orcan context add /abs/path` | Dodanie jednego projektu bez interakcji |
| `orcan context tui` | TUI: katalog-rodzic → multi-select repo → workspace (+ opcjonalnie wspólny branch worktree) |
| `orcan context add --from-worktree /abs/repo SELECTOR` | Dodanie istniejącego git worktree |
| `orcan context worktrees [/abs/repo]` | Lista worktree dla repo |
| `orcan context worktree create --repo … --branch …` | Utwórz worktree i podepnij |
| `orcan init /abs/path` | Pierwszy uruchomienie |
| Ręczna edycja JSON | Znasz schemat |

Pokaż bieżący układ:

```bash
orcan context show
```

## Co zapisuje `orcan sync`

`orcan.config.json` to historia, którą edytujesz. **`orcan sync`** to to, co Docker / Compose może łyknąć: odświeża pliki runtime hosta z tego JSON (+ UID/GID). Bez tego mounty i env zostają stare albo w ogóle ich nie ma.

| Wynik | Rola |
| --- | --- |
| `.env` | Zmienne Compose i Make |
| `mounts/runtime-config.json` | Montowany do kontenera jako `/etc/orcan/config.json` |
| `mounts/compose-projects.generated.yml` | Dodatkowe bind mounty |
| `mounts/compose-git.generated.yml` | Tworzone przez `orcan up --with-git` (mounty SSH) |
| `workspaces/<name>/` | Meta workspace'a po stronie hosta |
| Drzewo `$ORCAN_DATA` | Domyślnie `~/.config/orcan` (home Cursor/Claude, cache) |

Nie commituj `.env`, `mounts/` ani `workspaces/` (są w gitignore).

## Seed do checkoutów git (opcjonalnie, rzadko potrzebne)

**Workspace** i tak dostaje context pack przy starcie kontenera (`AGENTS.md`, ignores, `.cursor/rules/`). Do tego **`orcan seed` nie jest potrzebny**.

`orcan seed` tylko kopiuje podobne pliki **do każdego zamontowanego repo**. Pomiń, chyba że chcesz je mieć w samym checkoucie (np. żeby je commitować):

```bash
orcan seed --all
orcan seed --all --dry-run
```

Pełne reguły pól i odrzucane klucze: [Referencja konfiguracji](../reference/configuration.md).

## Zobacz też

- [Referencja konfiguracji](../reference/configuration.md)
- [Zmienne środowiskowe](../reference/environment.md)
- [Workspaces](../concepts/workspaces.md)
- [Szybki start](quickstart.md)
