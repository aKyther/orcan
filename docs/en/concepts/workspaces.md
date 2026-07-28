---
description: Deep dive on Orcan workspaces — why they exist, layout, and how they map to config.
---

# Workspaces

## Problem

A single repository is rarely the whole job. Without a name for “these checkouts belong together”, every person rebuilds the set ad hoc — and agents only see whatever directory they were started in.

## Why workspaces exist

A **workspace** is Orcan’s unit of **context**: one name, one session, one shared starter pack for agents, and one or more **projects** (repo paths).

It is more important than a single project when you use coding agents, because the agent needs the **bundle**.

Read [Core Ideas](../ideas/core-ideas.md) first if these terms are new.

## How it works

Each workspace becomes:

- a folder under `/home/developer/workspaces/<name>`
- one **tmux** session with the same name
- a **context pack** at that root (manifest, shared instructions, ignores)

Each project is a symlink for navigation **and** a path-parity bind mount for Docker.

## Example layout

```text
/home/developer/workspaces/myapp/     # workspace root
  .manifest.json
  AGENTS.md
  backend  → symlink to /absolute/path/to/backend
  frontend → symlink to /absolute/path/to/frontend
```

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

The first enabled workspace drives `WORKSPACE_ROOT` / `CONTAINER_PROJECT_DIR` in `.env` (entrypoint start directory).

## Trade-offs

- **Gain:** one named context you can recreate.  
- **Cost:** you must keep absolute paths accurate and run `orcan sync` after config edits.  
- **Choice:** Orcan does not rewrite every git checkout on start; seed projects explicitly when you want that.

## Git worktrees

A **git worktree** is another checkout of the same repository (separate path, usually another branch). Most of the time you just mount a normal clone path into a workspace and work on whatever branch is checked out.

Worktrees are **optional advanced help**: useful when you want a second checkout without touching the clone you use for `main` / pulls. Orcan can create those under `$ORCAN_DATA/worktrees/<workspace>/<project>/` and record them in `manifest.json`.

```bash
orcan context wizard   # mount paths; optionally create/pick a worktree per project

# Non-interactive (one repo):
orcan context worktree create --repo /abs/repo --branch topic --workspace my-ws --project backend
orcan context worktree remove --workspace my-ws   # or --path /abs/managed/checkout
```

Example after a managed worktree create:

```json
{
  "name": "my-ws",
  "projects": [
    { "name": "backend", "path": "/home/you/.config/orcan/worktrees/my-ws/backend" },
    { "name": "frontend", "path": "/home/you/.config/orcan/worktrees/my-ws/frontend" }
  ]
}
```

## Related

- [Mental Model](../ideas/mental-model.md)  
- [Path parity](path-parity.md)  
- [Architecture](../architecture.md)  
- [Configuration](../getting-started/configuration.md)
