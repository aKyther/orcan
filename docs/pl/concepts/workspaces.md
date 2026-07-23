# Workspaces

## Idea

**Workspace** grupuje jeden lub więcej projektów hosta w:

- jeden folder pod `/home/developer/workspaces/<name>`
- jedną sesję **tmux** o tej samej nazwie
- jeden context pack (manifest, ignores, instrukcje agentów)

## Układ

```text
/home/developer/workspaces/myapp/     # workspace root
  .manifest.json
  AGENTS.md
  backend  → symlink to /absolute/path/to/backend
  frontend → symlink to /absolute/path/to/frontend
```

Każde `projects[].path` jest też bind-montowane pod **tą samą ścieżką bezwzględną** (path parity). Symlinki służą nawigacji; mounty parity — Dockerowi z Dockera.

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
- `projects[].name` → nazwa symlinku
- `projects[].path` → bezwzględna ścieżka host/kontener

## Primary workspace

Pierwszy włączony workspace steruje `WORKSPACE_ROOT` / `CONTAINER_PROJECT_DIR` w `.env` (cel `cd` w entrypointcie).

## Zobacz też

- [Path parity](path-parity.md)
- [Architektura](architecture.md)
- [Konfiguracja](../getting-started/configuration.md)
