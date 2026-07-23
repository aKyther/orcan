# Workspaces

## Idea

A **workspace** groups one or more host projects into:

- one folder under `/home/developer/workspaces/<name>`
- one **tmux** session with the same name
- one context pack (manifest, ignores, agent instructions)

## Layout

```text
/home/developer/workspaces/myapp/     # workspace root
  .manifest.json
  AGENTS.md
  backend  → symlink to /absolute/path/to/backend
  frontend → symlink to /absolute/path/to/frontend
```

Each `projects[].path` is also bind-mounted at the **same absolute path** (path parity). Symlinks are for navigation; parity mounts are for Docker-from-Docker.

## Config mapping

```json
{
  "name": "myapp",
  "projects": [
    { "name": "backend", "path": "/absolute/path/to/backend" }
  ]
}
```

- `name` → session + workspace directory
- `projects[].name` → symlink name
- `projects[].path` → absolute host/container path

## Primary workspace

The first enabled workspace drives `WORKSPACE_ROOT` / `CONTAINER_PROJECT_DIR` in `.env` (entrypoint `cd` target).

## Related

- [Path parity](path-parity.md)
- [Architecture](architecture.md)
- [Configuration](../getting-started/configuration.md)
