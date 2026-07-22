# Multi-workspace launcher

Browser terminal (`ttyd`) starts a **workspace picker**, not a single tmux session.

## How it works

1. Open `http://localhost:7681` (main page — **workspaces**, good on Android)
2. Choose a workspace by number
3. Enter that workspace’s **tmux session** with default tabs: `workspace-1`, `workspace-2`, `workspace-3` (all start in workspace root).
4. Work in tmux as usual — rename tabs (`prefix ,`), add windows (`Alt+c`), `cd` into project subdirs. Run `agent` or `claude` when ready.
5. Refresh browser → launcher again → same workspace session if still alive

Each workspace lives under `/home/developer/workspaces/<name>` with 1+ mounted projects.

## Configure workspaces

```json
{
  "workspaces": [
    {
      "name": "gotibooks",
      "projects": [
        {"name": "backend", "path": "/home/you/gotibooks/backend"},
        {"name": "frontend", "path": "/home/you/gotibooks/frontend"}
      ]
    }
  ]
}
```

Default tmux tabs are plain names: `workspace-1`, `workspace-2`, `workspace-3`. Rename with `prefix ,` or add windows with `Alt+c`. Optional `projects[].windows[]` (with optional `icon`) exists for legacy per-project attach only — not used by the workspace launcher.

See [JSON config](config.md) and [Virtual workspace](architecture/workspace.md).
