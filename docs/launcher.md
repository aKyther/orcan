# Multi-workspace launcher

Browser terminal (`ttyd`) starts a **workspace picker**, not a single tmux session.

## How it works

1. Open `http://localhost:7681` (main page — **workspaces**, good on Android)
2. Choose a workspace by number
3. Enter that workspace’s **tmux session** with tabs:
   - **🖥 workspace** — workspace root
   - **one tab per project** (e.g. 🐍 backend, 🌐 frontend)
   - optional **extra tabs** per project via `projects[].windows[]`
4. Work in tmux as usual (tabs, panes, detach). Run `agent` or `claude` from workspace or `cd` into a project tab.
5. Refresh browser → launcher again → same workspace session if still alive

Each workspace lives under `/home/developer/workspaces/<name>` with 1+ mounted projects.

## Configure workspaces

```json
{
  "workspaces": [
    {
      "name": "gotibooks",
      "tmux": "gotibooks",
      "projects": [
        {"name": "backend", "path": "/home/you/gotibooks/backend", "windows": [
          {"name": "editor", "icon": "📝", "dir": "."},
          {"name": "server", "icon": "🐍", "dir": ".", "command": "make run"}
        ]},
        {"name": "frontend", "path": "/home/you/gotibooks/frontend"}
      ]
    }
  ]
}
```

See [JSON config](config.md) and [Virtual workspace](architecture/workspace.md).
