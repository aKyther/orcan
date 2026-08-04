---
description: Głębsze spojrzenie na workspace'y Orcana — po co istnieją, układ i mapowanie na konfigurację.
---

# Workspaces

## Problem

Pojedyncze repozytorium rzadko jest całą pracą. Bez nazwy dla „te checkouty należą do siebie” każdy odtwarza zbiór ad hoc — a agenci widzą tylko katalog, w którym ich uruchomiono.

## Dlaczego workspace'y istnieją

**Workspace** to jednostka **kontekstu** w Orcanie: jedna nazwa, jedna sesja, jeden wspólny pack startowy dla agentów oraz jeden lub więcej **projektów** (ścieżki repo).

Jest ważniejszy niż pojedynczy projekt przy agentach kodujących, bo agent potrzebuje **wiązki**.

Jeśli terminy są nowe, najpierw [Idee podstawowe](../ideas/core-ideas.md).

## Jak to działa

Każdy workspace staje się:

- folderem pod `/home/developer/workspaces/<name>`
- jedną sesją **tmux** o tej samej nazwie
- **context packiem** w tym rootcie (manifest, wspólne instrukcje, ignores)

Każdy projekt to symlink do nawigacji **oraz** bind mount path-parity dla Dockera.

## Przykładowy układ

```text
/home/developer/workspaces/myapp/     # root workspace'a
  .manifest.json
  AGENTS.md
  backend  → symlink do /absolute/path/to/backend
  frontend → symlink do /absolute/path/to/frontend
```

## Mapowanie konfiguracji

```json
{
  "name": "myapp",
  "projects": [
    { "name": "backend", "path": "/absolute/path/to/backend" }
  ]
}
```

- `name` → sesja + katalog workspace'a  
- `projects[].name` → nazwa symlinka  
- `projects[].path` → bezwzględna ścieżka host/kontener  

## Primary workspace

Pierwszy włączony workspace napędza `WORKSPACE_ROOT` / `CONTAINER_PROJECT_DIR` w `.env` (katalog startu entrypointu).

## Kompromisy

- **Zysk:** jeden nazwany kontekst do odtworzenia.  
- **Koszt:** musisz utrzymywać poprawne ścieżki bezwzględne i uruchamiać `orcan sync` po edycji konfiguracji.  
- **Wybór:** Orcan nie przepisuje każdego checkoutu git przy starcie; seeduj projekty jawnie, gdy tego chcesz.

## Git worktree

**Git worktree** to kolejny checkout tego samego repozytorium (inna ścieżka, zwykle inny branch). Na co dzień wystarczy zamontować zwykłą ścieżkę klona w workspace i pracować na tym branchu, który tam jest.

Worktree to **opcjonalna, zaawansowana pomoc**: gdy chcesz drugi checkout bez ruszania klona od `main` / `pull`. Orcan może je tworzyć pod `$ORCAN_DATA/worktrees/<workspace>/<project>/` i zapisać w `manifest.json`.

```bash
orcan init   # montuj ścieżki; opcjonalnie utwórz/wybierz worktree

# Bez interakcji (jedno repo):
orcan context worktree create --repo /abs/repo --branch topic --workspace my-ws --project backend
orcan context worktree remove --workspace my-ws   # albo --path /abs/managed/checkout
```

Przykład po managed create:

```json
{
  "name": "my-ws",
  "projects": [
    { "name": "backend", "path": "/home/you/.config/orcan/worktrees/my-ws/backend" },
    { "name": "frontend", "path": "/home/you/.config/orcan/worktrees/my-ws/frontend" }
  ]
}
```

## Powiązane

- [Model mentalny](../ideas/mental-model.md)  
- [Path parity](path-parity.md)  
- [Architektura](../architecture.md)  
- [Konfiguracja](../getting-started/configuration.md)
