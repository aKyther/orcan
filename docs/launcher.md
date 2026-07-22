# Multi-workspace launcher

Browser terminal (`ttyd`) starts a **workspace picker**, not a single tmux session.

## How it works

1. Open `http://localhost:7681`
2. Choose a workspace by number
3. Enter a dedicated tmux session for that workspace (one window per project by default)
4. Run `agent` in the workspace root or `cd` into a project subdirectory
5. Detach or refresh the page → picker again → same session if it still exists

Each workspace lives under `/home/developer/workspaces/<name>` with 1+ mounted projects.

## Configure workspaces

```json
{
  "workspaces": [
    {
      "name": "gotibooks",
      "tmux": "gotibooks",
      "projects": [
        {"name": "backend", "path": "/home/you/gotibooks/backend"},
        {"name": "frontend", "path": "/home/you/gotibooks/frontend"}
      ]
    }
  ]
}
```

See [JSON config](config.md) and [Virtual workspace](architecture/workspace.md).
