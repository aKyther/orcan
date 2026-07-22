# Virtual workspace architecture

A **workspace** is the primary unit in cind: one directory under `/home/developer/workspaces/<name>`, one tmux session, one or more mounted repos.

## Model

```text
Host (meta)                           Container
──────────────────────────────────    ─────────────────────────────────────
.cind/workspaces/gotibooks/      →    /home/developer/workspaces/gotibooks/
  .cursor/rules/                         .cursor/rules/
  backend/  → symlink or bind            backend/   (project checkout)
  frontend/                              frontend/
```

| Path | Purpose |
| --- | --- |
| `meta_path` (host) | Persistent workspace files: `.cursor/rules`, docs |
| `root` (container) | Default `/home/developer/workspaces/<name>` — agent starts here |
| `projects[].name` | Subdirectory under workspace root |
| `projects[].path` | Host absolute path (source of mount) |
| `tmux` / `tmux_session` | tmux session name (defaults to workspace `name`) |

## One tmux session per workspace

- ttyd launcher lists **workspaces**.
- Choosing a workspace attaches **one** tmux session.
- Default layout: **one window per project** (🐍 backend, 🌐 frontend, …).
- Agent and shell start in the **workspace root**; projects are subdirectories.

## Configuration

```json
{
  "workspaces": [
    {
      "name": "gotibooks",
      "mount_mode": "parity",
      "tmux": "gotibooks",
      "projects": [
        {"name": "backend", "path": "/home/you/gotibooks/backend"},
        {"name": "frontend", "path": "/home/you/gotibooks/frontend"}
      ]
    }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `name` | Workspace id — directory name under `/home/developer/workspaces/` |
| `tmux` | tmux session (optional; defaults to `name`) |
| `projects[]` | Repos mounted as `<root>/<name>/` |
| `mount_mode` | Default mount for projects: `parity` or `workspace` |

No `alias`, no `default_project`, no `default_workspace`.

## Mount modes

`parity`: host path exists 1:1 in container (Docker socket use).

`workspace`: host path bound only under workspace root (code review / analysis).

Details: [Mount modes](mount-modes.md).

## Workspace-level Cursor rules

Place rules in `<meta_path>/.cursor/rules/` on the host.

## Agents

Read `<workspace.root>/.manifest.json` for projects, host paths, and mount modes.

Do not treat workspace root as a git root.
