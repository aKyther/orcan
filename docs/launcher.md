# Multi-workspace launcher

Browser terminal (`ttyd`) starts a **workspace picker**, not a single tmux session.

## How it works

1. Open `http://localhost:7681`
2. Choose a workspace by number — each choice is its own **tmux session**
3. Land in that session with tabs `tab-1` … `tab-3` (all in that workspace root)
4. Work as usual — `cd` into project subdirs, run `agent` / `claude`
5. **Detach** (`Ctrl+Space` then `d`) → back to the launcher → pick another workspace
6. Switch between workspaces **without leaving tmux**: `Ctrl+Space` then `w` (or `s`) — all sessions are created when the launcher opens

| Concept | Meaning |
| --- | --- |
| Workspace (`orcan.config.json`) | One session + one directory under `/home/developer/workspaces/<name>` |
| tmux **session** | That workspace (name = `workspaces[].name`) — all bootstrapped in the background |
| tmux **tab** (`tab-1` …) | Extra shell in the **same** workspace — not another workspace |

## Configure workspaces

```bash
make config-wizard
make env
make down && make terminal-docker
```

Or edit `orcan.config.json` by hand:

```json
{
  "workspaces": [
    {
      "name": "gotibooks",
      "projects": [
        { "name": "backend", "path": "/home/you/gotibooks/backend" },
        { "name": "frontend", "path": "/home/you/gotibooks/frontend" }
      ]
    },
    {
      "name": "orcan",
      "projects": [
        { "name": "orcan", "path": "/home/you/workspace/kyther/orcan" }
      ]
    }
  ]
}
```

After editing config: `make env && make down && make terminal-docker`.

See [Config](config.md) and [Virtual workspace](architecture/workspace.md).
